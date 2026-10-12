"""웹 중계 서버(webapi) 테스트. 실제 Dify 대신 가짜 응답(MockTransport)을, 기록·문서는 임시 파일을 쓴다.
실험 결과·소개 데이터는 실제 결과 파일(C:/curation-data)이 있을 때만 확인한다."""
import json
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from webapi import app as A
from webapi.config import Settings

REAL_RUNS = Path("C:/curation-data/runs")


def _settings(tmp_path, key="", runs_root=None):
    return Settings(dify_api_base="http://dify.test/v1", dify_api_key=key, tools_host="127.0.0.1", tools_port=1,
                    runs_root=runs_root or tmp_path, events_path=tmp_path / "events.jsonl", web_dist=tmp_path / "dist",
                    kb_dir=tmp_path / "kb")


def _mock_dify(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(A.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(A.dify.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def _sse_events(text: str) -> list[dict]:
    return [json.loads(b[5:]) for b in text.strip().split("\n\n") if b.startswith("data:")]


def test_health_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    r = TestClient(A.app).get("/api/health").json()
    assert r["dify"] == {"ok": False, "detail": "API 키 없음 (webapi/.env의 DIFY_API_KEY)"}
    assert r["tools"]["ok"] is False  # 1번 포트에는 아무것도 없다


@pytest.mark.parametrize("status,ok,detail", [(200, True, "시범데이터 선별 에이전트"), (401, False, "API 키가 맞지 않음")])
def test_health_dify_key(tmp_path, monkeypatch, status, ok, detail):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(status, json={"name": "시범데이터 선별 에이전트"})

    _mock_dify(monkeypatch, handler)
    r = TestClient(A.app).get("/api/health").json()
    assert r["dify"] == {"ok": ok, "detail": detail}
    assert seen["auth"] == "Bearer app-test"


def test_chat_relays_dify_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent["body"] = json.loads(req.content)
        body = ('event: ping\n\n'
                'data: {"event": "workflow_started", "conversation_id": "c1"}\n\n'
                'data: {"event": "human_input_required", "data": {"form_token": "tok"}}\n\n'
                'data: {"event": "workflow_paused", "workflow_run_id": "w1"}\n\n')
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    _mock_dify(monkeypatch, handler)
    r = TestClient(A.app).post("/api/chat", json={"query": "can 150개"})
    evs = _sse_events(r.text)
    assert [e["event"] for e in evs] == ["workflow_started", "human_input_required", "workflow_paused"]  # ping은 거름
    assert sent["body"]["user"] == "web-demo" and sent["body"]["response_mode"] == "streaming"


def test_chat_adds_evidence_after_retrieval(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "01_x.md").write_text("---\ntitle: X Datasets\nsource_url: https://example.org/x\n---\nbody\n", encoding="utf-8")
    node = {"event": "node_finished", "data": {"node_type": "knowledge-retrieval", "outputs": {"result": [
        {"title": "01_x.md", "content": "Dataset types: MH\n[X Datasets | 문헌 근거 | https://example.org/x]\nSix operators.",
         "metadata": {"document_name": "01_x.md", "score": 0.9}}]}}}

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"data: {json.dumps(node)}\n\n")

    _mock_dify(monkeypatch, handler)
    evs = _sse_events(TestClient(A.app).post("/api/chat", json={"query": "MH?"}).text)
    assert [e["event"] for e in evs] == ["node_finished", "evidence"]
    d = evs[1]["docs"][0]
    assert (d["title"], d["source_url"], d["score"], d["section"], d["chunk"]) == ("X Datasets", "https://example.org/x", 0.9,
                                                                                   "Dataset types: MH", "Six operators.")


def test_approve_submits_then_streams_and_final(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, dict(req.url.params)))
        if req.url.path.endswith("/form/human_input/tok"):
            assert json.loads(req.content) == {"inputs": {}, "action": "approve", "user": "web-demo"}
            return httpx.Response(200, json={})
        if req.url.path.endswith("/workflow/w1/events"):
            return httpx.Response(200, text='data: {"event": "message", "answer": "승인되었습니다"}\n\n'
                                             'data: {"event": "workflow_finished"}\n\n')
        if req.url.path.endswith("/messages"):
            return httpx.Response(200, json={"data": [{"id": "m1", "answer": "전체 답변", "status": "normal",
                                                       "metadata": {"usage": {"total_price": "0.0014"}}}]})
        return httpx.Response(404)

    _mock_dify(monkeypatch, handler)
    r = TestClient(A.app).post("/api/approve", json={"form_token": "tok", "action": "approve", "workflow_run_id": "w1",
                                                     "conversation_id": "c1"})
    evs = _sse_events(r.text)
    assert [e["event"] for e in evs] == ["form_submitted", "message", "workflow_finished", "final_message"]
    assert evs[-1]["answer"] == "전체 답변" and evs[-1]["usage"]["total_price"] == "0.0014"
    assert calls[1][2]["include_state_snapshot"] == "true"  # 제출과 구독 사이 이벤트를 놓치지 않게


def test_approve_rejects_bad_action(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    r = TestClient(A.app).post("/api/approve", json={"form_token": "tok", "action": "maybe", "workflow_run_id": "w1"})
    assert r.status_code == 400


def _write_events(path: Path):
    rows = [
        {"ts": "2026-10-12T12:21:38.561", "session_id": "s1", "tool": "analyze_data", "event": "tool_start", "args": {"dataset": "can_mh"}},
        {"ts": "2026-10-12T12:21:39.143", "session_id": "s1", "tool": "analyze_data", "event": "tool_end", "duration_sec": 0.582},
        {"ts": "2026-10-12T12:21:40.702", "session_id": "s1", "tool": "select_demos", "event": "tool_start", "args": {"budget": 150}},
        {"ts": "2026-10-12T12:21:40.934", "session_id": "s1", "tool": "select_demos", "event": "tool_end", "run_id": "R-x-select-1", "duration_sec": 0.231},
        {"ts": "2026-10-12T12:21:45.115", "session_id": "s1", "tool": "review_selection", "event": "review", "verdict": "pass", "run_id": "R-x-select-1"},
        {"ts": "2026-10-12T12:21:46.037", "session_id": "s1", "tool": "log_event", "event": "agent_log", "agent_event": "approved", "run_id": "R-x-select-1"},
        {"ts": "2026-10-12T13:00:00.000", "session_id": "s2", "tool": "review_selection", "event": "review", "verdict": "pass", "run_id": "R-y-select-2"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_runs_and_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    _write_events(tmp_path / "events.jsonl")
    c = TestClient(A.app)
    rows = c.get("/api/runs").json()["runs"]
    assert [r["session_id"] for r in rows] == ["s2", "s1"]  # 최근 것부터
    s1 = rows[1]
    assert (s1["dataset"], s1["budget"], s1["review"], s1["approval"], s1["selection_run"]) == ("can_mh", 150, "pass", "approved", "R-x-select-1")
    assert rows[0]["approval"] == "waiting"  # 검수 통과 후 승인 기록이 없으면 대기
    d = c.get("/api/runs/s1").json()
    assert d["events"][1]["t"] == 0.582 and "raw" not in d
    dl = c.get("/api/runs/s1?download=1")
    assert "attachment" in dl.headers["content-disposition"] and len(dl.json()) == 6
    assert c.get("/api/runs/none").status_code == 404


def test_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "01_x.md").write_text("---\ntitle: X Datasets\nsource_url: https://example.org/x\ndoc_type: 문헌 근거\n---\n\n# X\n"
                                "## MH\n[X Datasets | 문헌 근거 | https://example.org/x]\nSix operators.\n", encoding="utf-8")
    c = TestClient(A.app)
    assert c.get("/api/docs").json()["docs"][0]["source_url"] == "https://example.org/x"
    d = c.get("/api/docs/01_x.md").json()
    assert d["title"] == "X Datasets" and "Six operators." in d["content"] and "example.org" not in d["content"]
    assert c.get("/api/docs/..%2Fsecret.md").status_code == 404


def test_unknown_api_is_404_json(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    r = TestClient(A.app).get("/api/nothing")
    assert r.status_code == 404 and r.json()["detail"] == "없는 API입니다"


@pytest.mark.skipif(not (REAL_RUNS / "R-20261011-select-main").exists(), reason="실험 결과 파일 없음")
def test_results_and_overview_real(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, runs_root=REAL_RUNS))
    c = TestClient(A.app)
    res = c.get("/api/results").json()
    assert res["can"]["fingerprint"] == "c15466d53a01cedb" and "gain_vs_random" in res["can"]["paired"]
    assert res["square"]["fingerprint"] == "7d9cc28398190719"
    ov = c.get("/api/overview").json()
    assert len(ov["points"]) == 270 and sum(p[2] for p in ov["points"]) == 150
    assert ov["selected"] == {"n_demos": 150, "total_frames": 21833} and ov["signals"][0]["name"] == "length"


def test_spa_without_build(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    r = TestClient(A.app).get("/demo")
    assert r.status_code == 404 and "빌드" in r.json()["detail"]
