"""Dify 앱 API 중계: 채팅(실시간 흐름), 승인 제출과 이어지는 흐름, 최종 메시지.

흐름 (Dify 1.17 service API, 2026-10-12 서버 코드로 확인)
1. POST /chat-messages (streaming) → 승인 노드에서 human_input_required(form_token) + workflow_paused(workflow_run_id) 후 닫힘
2. POST /form/human_input/{form_token} {inputs, action, user} → 실행 재개 (승인 노드가 "웹앱 전달"이어야 함)
3. GET /workflow/{workflow_run_id}/events?user=..&include_state_snapshot=true → 이어지는 이벤트.
   제출과 구독 사이에 지나간 이벤트를 놓치지 않으려고 지난 상태부터 다시 받는다
4. 흐름이 끝나면 GET /messages?conversation_id=..로 최종 답변·사용량·근거 문서를 받아 final_message로 붙인다

모든 호출의 user는 WEB_USER로 고정한다 (Dify는 실행을 만든 user만 이어서 볼 수 있게 한다).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

WEB_USER = "web-demo"
RESUBSCRIBE = 10  # 승인 뒤 이어지는 흐름 구독 최대 횟수
END_EVENTS = {"workflow_finished", "workflow_paused", "error"}
APPROVE_END_EVENTS = {"workflow_finished", "error"}


def _event_key(e: dict) -> str:
    """같은 이벤트를 두 번 보내지 않으려고 쓰는 키. 노드 이벤트는 실행 ID로, 나머지는 내용 전체로."""
    d = e.get("data") or {}
    if e.get("event", "").startswith("node_") or e.get("event") == "workflow_started":
        return f"{e.get('event')}:{d.get('id')}:{d.get('status')}"
    return json.dumps(e, sort_keys=True, ensure_ascii=False)


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")


async def _relay(resp: httpx.Response) -> AsyncIterator[bytes]:
    """Dify의 SSE를 이벤트 단위로 그대로 넘긴다. 핑(event: ping)과 빈 줄은 거른다."""
    buf = ""
    async for chunk in resp.aiter_text():
        buf += chunk
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            data = [ln[5:].strip() for ln in block.splitlines() if ln.startswith("data:")]
            if data and data[0]:
                yield f"data: {data[0]}\n\n".encode("utf-8")


async def chat_stream(base: str, key: str, query: str, conversation_id: str = "") -> AsyncIterator[bytes]:
    body = {"inputs": {}, "query": query, "response_mode": "streaming", "conversation_id": conversation_id, "user": WEB_USER}
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=180)) as c:
        async with c.stream("POST", f"{base}/chat-messages", headers=_headers(key), json=body) as r:
            if r.status_code != 200:
                yield sse({"event": "error", "status": r.status_code, "message": (await r.aread()).decode("utf-8", "replace")[:500]})
                return
            async for ev in _relay(r):
                yield ev


async def final_message(base: str, key: str, conversation_id: str) -> dict | None:
    """대화의 마지막 메시지 (답변 전체, 사용량, 근거 문서)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{base}/messages", headers=_headers(key),
                        params={"conversation_id": conversation_id, "user": WEB_USER, "limit": 1})
    if r.status_code != 200:
        return None
    data = r.json().get("data") or []
    if not data:
        return None
    m = data[-1]
    meta = m.get("metadata") or {}
    return {"message_id": m.get("id"), "answer": m.get("answer", ""), "status": m.get("status"),
            "usage": meta.get("usage"), "retriever_resources": m.get("retriever_resources") or meta.get("retriever_resources") or []}


async def approve_stream(base: str, key: str, form_token: str, action: str, workflow_run_id: str,
                         conversation_id: str, inputs: dict | None = None) -> AsyncIterator[bytes]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=180)) as c:
        r = await c.post(f"{base}/form/human_input/{form_token}", headers=_headers(key),
                         json={"inputs": inputs or {}, "action": action, "user": WEB_USER})
        if r.status_code != 200:
            yield sse({"event": "error", "status": r.status_code, "message": r.text[:500]})
            return
        yield sse({"event": "form_submitted", "action": action})
        params = {"user": WEB_USER, "include_state_snapshot": "true"}
        # 제출 직후에 구독하면 실행이 아직 재개되지 않아 멈춤 상태만 받고 닫히는 때가 있다 (2026-10-17 실제 대화에서 1번 확인).
        # 끝 이벤트를 받을 때까지 1초 뒤 다시 구독하고, 이미 보낸 이벤트는 다시 보내지 않는다
        sent: set[str] = set()
        finished_answer = None
        for attempt in range(RESUBSCRIBE):
            if attempt:
                await asyncio.sleep(1)
            done = False
            async with c.stream("GET", f"{base}/workflow/{workflow_run_id}/events", headers=_headers(key), params=params) as s:
                if s.status_code != 200:
                    yield sse({"event": "error", "status": s.status_code, "message": (await s.aread()).decode("utf-8", "replace")[:500]})
                    break
                async for ev in _relay(s):
                    e = json.loads(ev[5:])
                    k = _event_key(e)
                    if k in sent:
                        continue
                    sent.add(k)
                    # 지난 상태(snapshot)에는 승인 전의 멈춤 이벤트가 다시 들어 있다. 승인 뒤에는 완료·오류만 끝으로 본다
                    # (멈춤을 끝으로 보면 보고가 나오기 전에 구독을 닫아 빈 답이 나간다, 2026-10-20 리허설에서 확인)
                    done = done or e.get("event") in APPROVE_END_EVENTS
                    if e.get("event") == "workflow_finished":
                        finished_answer = ((e.get("data") or {}).get("outputs") or {}).get("answer")
                    yield ev
            if done:
                break
    if conversation_id:
        m = await final_message(base, key, conversation_id)
        # 끝나자마자 메시지를 읽으면 저장 전의 답(승인 전 내용)이 올 때가 있다. 끝 이벤트에 든 최종 답을 우선 쓴다
        if finished_answer:
            m = {**(m or {"message_id": None, "status": "normal", "usage": None, "retriever_resources": []}), "answer": finished_answer}
        if m:
            yield sse({"event": "final_message", **m})
