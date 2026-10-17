"""중계 서버 (Starlette). 화면(web/)이 부르는 /api를 Dify 앱 API·MCP 도구 서버·결과 파일로 잇는다.

실행: python -m webapi  (curation-agent 폴더에서, conda env curation) → http://127.0.0.1:8900
개발 중 화면은 web/에서 npm run dev (http://localhost:5173, /api는 이 서버로 넘어옴)

API
  GET  /api/health                 Dify(키 확인 포함)·도구 서버 연결 상태
  POST /api/chat                   {query, conversation_id?} → Dify 이벤트 실시간 흐름 (SSE)
  POST /api/approve                {form_token, action, workflow_run_id, conversation_id} → 이어지는 흐름 + final_message
  GET  /api/message/{대화ID}        마지막 메시지 (답변, 사용량, 근거 문서)
  GET  /api/runs                   실행 기록 목록 (events.jsonl, 대화별 요약)
  GET  /api/runs/{대화ID}           대화의 이벤트 (?download=1이면 원본 JSON 파일로)
  POST /api/check/{대화ID}          보고 수치 검사 {answer?}. 없으면 Dify에서 마지막 답변을 가져와 검사
  GET  /api/results                Can 150 / Can 135 / Square 결과와 판정
  GET  /api/overview               소개 페이지 데이터 (산점도, 품질 신호, 구성)
  GET  /api/docs, /api/docs/{파일}   근거 문서 목록, 원문 링크와 전체 내용
  GET  /api/kit/{실행ID}/{파일}       학습 키트 파일 내려받기 (노트북 2종, 학습 설정, 사용법, 고른 데이터 파일)
  POST /api/results/{대화ID}         학습 결과 파일(JSON 본문)을 올려 판정 (선별 효과 판정 또는 결과 확인)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from curation_tools import judge
from webapi import data, dify
from webapi.config import Settings, load

settings: Settings = load()

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _no_key() -> JSONResponse:
    return JSONResponse({"detail": "Dify API 키가 없습니다 (webapi/.env의 DIFY_API_KEY)"}, status_code=503)


async def _check_dify() -> dict:
    """Dify에 닿는지, 그리고 API 키가 맞는지 본다 (/v1/info는 키가 맞아야 200)."""
    if not settings.dify_api_key:
        return {"ok": False, "detail": "API 키 없음 (webapi/.env의 DIFY_API_KEY)"}
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{settings.dify_api_base}/info", headers={"Authorization": f"Bearer {settings.dify_api_key}"})
        if r.status_code == 200:
            return {"ok": True, "detail": r.json().get("name", "연결됨")}
        if r.status_code == 401:
            return {"ok": False, "detail": "API 키가 맞지 않음"}
        return {"ok": False, "detail": f"Dify 응답 {r.status_code}"}
    except httpx.HTTPError as e:
        return {"ok": False, "detail": f"Dify에 연결할 수 없음 ({type(e).__name__})"}


async def _check_tools() -> dict:
    """MCP 도구 서버 포트가 열려 있는지 본다."""
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(settings.tools_host, settings.tools_port), timeout=2)
        w.close()
        await w.wait_closed()
        return {"ok": True, "detail": f"{settings.tools_host}:{settings.tools_port}"}
    except (OSError, asyncio.TimeoutError):
        return {"ok": False, "detail": f"{settings.tools_host}:{settings.tools_port} 응답 없음"}


async def health(request: Request) -> JSONResponse:
    d, t = await asyncio.gather(_check_dify(), _check_tools())
    return JSONResponse({"dify": d, "tools": t})


async def _body(request: Request) -> dict:
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):  # UTF-8이 아닌 본문도 빈 요청으로 본다 (500 대신 400)
        return {}


async def chat(request: Request):
    if not settings.dify_api_key:
        return _no_key()
    b = await _body(request)
    query = (b.get("query") or "").strip()
    if not query:
        return JSONResponse({"detail": "query가 비었습니다"}, status_code=400)
    stream = dify.chat_stream(settings.dify_api_base, settings.dify_api_key, query, b.get("conversation_id") or "")
    return StreamingResponse(_with_evidence(stream), media_type="text/event-stream", headers=SSE_HEADERS)


async def _with_evidence(stream):
    """Dify 흐름을 그대로 넘기면서, 근거 검색 노드가 끝나면 화면용 evidence 이벤트를 하나 더 보낸다."""
    async for ev in stream:
        yield ev
        try:
            e = json.loads(ev.decode("utf-8")[5:])
        except (ValueError, UnicodeDecodeError):
            continue
        d = e.get("data") or {}
        if e.get("event") == "node_finished" and d.get("node_type") == "knowledge-retrieval":
            yield dify.sse({"event": "evidence", "docs": data.evidence(d.get("outputs") or {}, settings.kb_dir)})


async def approve(request: Request):
    if not settings.dify_api_key:
        return _no_key()
    b = await _body(request)
    if b.get("action") not in ("approve", "reject") or not b.get("form_token") or not b.get("workflow_run_id"):
        return JSONResponse({"detail": "form_token, workflow_run_id, action(approve|reject)이 필요합니다"}, status_code=400)
    stream = dify.approve_stream(settings.dify_api_base, settings.dify_api_key, b["form_token"], b["action"],
                                 b["workflow_run_id"], b.get("conversation_id") or "")
    return StreamingResponse(stream, media_type="text/event-stream", headers=SSE_HEADERS)


async def message(request: Request):
    if not settings.dify_api_key:
        return _no_key()
    m = await dify.final_message(settings.dify_api_base, settings.dify_api_key, request.path_params["sid"])
    return JSONResponse(m) if m else JSONResponse({"detail": "메시지를 찾을 수 없습니다"}, status_code=404)


async def runs(request: Request) -> JSONResponse:
    return JSONResponse({"runs": data.runs(settings.events_path)})


async def run_detail(request: Request):
    sid = request.path_params["sid"]
    d = data.run_detail(settings.events_path, sid)
    if d is None:
        return JSONResponse({"detail": "기록이 없는 대화입니다"}, status_code=404)
    if request.query_params.get("download"):
        body = json.dumps(d["raw"], ensure_ascii=False, indent=1)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="events_{sid[:8]}.json"'})
    return JSONResponse({k: v for k, v in d.items() if k != "raw"})


async def check(request: Request):
    sid = request.path_params["sid"]
    answer = (await _body(request)).get("answer")
    if not answer:
        if not settings.dify_api_key:
            return _no_key()
        m = await dify.final_message(settings.dify_api_base, settings.dify_api_key, sid)
        if not m:
            return JSONResponse({"detail": "이 대화의 답변을 Dify에서 찾을 수 없습니다 (웹에서 만든 대화만 가져올 수 있음). answer를 직접 보내 주세요"},
                                status_code=404)
        answer = m["answer"]
    return JSONResponse(data.check(answer, settings.events_path, sid, settings.runs_root))


async def results(request: Request) -> JSONResponse:
    return JSONResponse(data.results(settings.runs_root))


async def overview(request: Request) -> JSONResponse:
    return JSONResponse(data.overview(settings.runs_root))


async def docs(request: Request) -> JSONResponse:
    return JSONResponse({"docs": data.docs(settings.kb_dir)})


async def doc(request: Request):
    d = data.doc(settings.kb_dir, request.path_params["name"])
    return JSONResponse(d) if d else JSONResponse({"detail": "문서를 찾을 수 없습니다"}, status_code=404)


KIT_FILES = ("train_curated.ipynb", "train_compare.ipynb", "train_settings.json", "README.txt", "kit.json")
SID_RE = re.compile(r"^[0-9A-Za-z_-]{1,80}$")
RUN_ID_RE = re.compile(r"^R-[0-9A-Za-z_-]{1,60}$")
MAX_RESULT_BYTES = 20 * 1024 * 1024


async def kit_file(request: Request):
    """학습 키트 파일 내려받기. 정해진 키트 파일과 선별이 만든 데이터 파일(<데이터>_curated.hdf5)만 준다."""
    run_id, name = request.path_params["run_id"], request.path_params["name"]
    if not RUN_ID_RE.match(run_id):
        return JSONResponse({"detail": "잘못된 실행 ID"}, status_code=400)
    run_dir = settings.runs_root / run_id
    if name in KIT_FILES:
        path = run_dir / "kit" / name
    elif re.fullmatch(r"[0-9A-Za-z_]{1,60}_curated\.hdf5", name):
        path = run_dir / name
    else:
        return JSONResponse({"detail": "키트 파일이 아닙니다"}, status_code=400)
    if not path.is_file():
        return JSONResponse({"detail": "파일이 없습니다 (키트를 먼저 만드세요)"}, status_code=404)
    return FileResponse(path, filename=name)


async def upload_result(request: Request) -> JSONResponse:
    """학습 결과 파일(키트 노트북의 results_main_<지문>.json)을 받아 판정한다. 본문은 파일 내용 그대로 (JSON)."""
    sid = request.path_params["sid"]
    if not SID_RE.match(sid):
        return JSONResponse({"detail": "잘못된 대화 ID"}, status_code=400)
    raw = await request.body()
    if len(raw) > MAX_RESULT_BYTES:
        return JSONResponse({"detail": "결과 파일이 너무 큽니다 (20MB 이하)"}, status_code=413)
    try:
        doc = json.loads(raw.decode("utf-8"))
        res = judge.judge(doc, settings.runs_root)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"detail": "JSON 파일이 아닙니다"}, status_code=400)
    except (ValueError, KeyError, TypeError) as e:
        return JSONResponse({"detail": f"판정할 수 없는 결과 파일입니다: {e}"}, status_code=400)
    saved = judge.save(doc, res, settings.runs_root, sid)
    # Dify에서 "학습 결과 보여줘"라고 하면 이 판정을 보여 주도록 도구 서버와 같은 형식으로 기록한다
    rec = {"ts": dt.datetime.now().isoformat(timespec="milliseconds"), "session_id": sid, "tool": "web", "event": "judged",
           "run_id": res["run_id"], "kind": res["kind"], "judgement_path": str(saved)}
    settings.events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return JSONResponse(res)


async def spa(request: Request):
    """빌드한 화면이 있으면 그 index.html을 돌려준다 (새로고침해도 /demo 같은 주소가 열리게)."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "없는 API입니다"}, status_code=404)
    index = settings.web_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "화면이 빌드되지 않았습니다. web 폴더에서 npm run dev 또는 npm run build"}, status_code=404)


routes = [
    Route("/api/health", health),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/approve", approve, methods=["POST"]),
    Route("/api/message/{sid}", message),
    Route("/api/runs", runs),
    Route("/api/runs/{sid}", run_detail),
    Route("/api/check/{sid}", check, methods=["POST"]),
    Route("/api/results", results),
    Route("/api/overview", overview),
    Route("/api/docs", docs),
    Route("/api/docs/{name}", doc),
    Route("/api/kit/{run_id}/{name}", kit_file),
    Route("/api/results/{sid}", upload_result, methods=["POST"]),
]
app = Starlette(routes=routes)
if (settings.web_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets")
app.add_route("/{path:path}", spa)
