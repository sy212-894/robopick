"""curation-tools MCP 서버 테스트. 서버를 띄우지 않고 메모리 안에서 MCP 클라이언트로 도구를 호출한다.

실행: python -m pytest tests -q
"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from curation_tools import server as srv

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = [pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음"), pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # 실제 runs 폴더와 기록 파일을 건드리지 않도록 임시 폴더로 바꾼다
    monkeypatch.setattr(srv, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(srv, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(srv, "DATASETS", {"can_mh": DATA})
    return tmp_path


async def call(session, name, args):
    res = await session.call_tool(name, args)
    return res, (json.loads(res.content[0].text) if res.content else None)


def events(tmp_path):
    return [json.loads(l) for l in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]


async def test_tools_listed():
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        names = {t.name for t in (await s.list_tools()).tools}
    assert names == {"analyze_data", "select_demos", "review_selection", "train_evaluate", "log_event"}


async def test_analyze_then_select(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        res, a = await call(s, "analyze_data", {"dataset": "can_mh", "session_id": "conv-1"})
        assert not res.isError and a["dataset"]["n_demos"] == 300 and len(a["conditions"]) == 9
        res, sel = await call(s, "select_demos", {"analysis_run_id": a["run_id"], "session_id": "conv-1"})
        assert not res.isError
    assert sel["checks"]["verdict"] == "pass"
    assert sel["sets"]["curated_150"]["n_demos"] == 150
    # LLM에 가는 응답에는 시범 ID와 숙련도 라벨이 없어야 한다
    text = json.dumps(a) + json.dumps(sel)
    assert "demo_" not in text and "better" not in text and "worse" not in text
    ev = events(isolated)
    assert [e["event"] for e in ev] == ["tool_start", "tool_end", "tool_start", "tool_end"]
    assert all(e["session_id"] == "conv-1" for e in ev)
    assert ev[3]["run_id"] == sel["run_id"]


@pytest.mark.parametrize("args", [
    {"analysis_run_id": "../raw"},                 # 경로 이동 시도
    {"analysis_run_id": "C:/curation-data/raw"},  # 절대 경로
    {"analysis_run_id": "R-does-not-exist"},       # 없는 실행
    {"analysis_run_id": "R-x", "budget": 5000},    # 예산 범위 밖
])
async def test_select_rejects_bad_args(args):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        res, _ = await s.call_tool("select_demos", args), None
    assert res.isError


async def test_analyze_rejects_unknown_dataset():
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        res = await s.call_tool("analyze_data", {"dataset": "C:/Windows/win.ini"})
    assert res.isError


async def test_log_event(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        res, out = await call(s, "log_event", {"stage": "approval", "event": "approved",
                                               "detail": "사람이 학습 계획 승인", "session_id": "conv-1"})
        bad = await s.call_tool("log_event", {"stage": "x", "event": "y", "session_id": "bad id!"})
    assert out == {"ok": True} and bad.isError
    ev = events(isolated)
    assert ev[-1]["stage"] == "approval" and ev[-1]["agent_event"] == "approved"


async def test_review_selection(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        # 선별 전에는 검수할 것이 없다
        _, none = await call(s, "review_selection", {"session_id": "conv-r"})
        assert none["verdict"] == "none"
        _, a = await call(s, "analyze_data", {"session_id": "conv-r"})
        _, sel = await call(s, "select_demos", {"analysis_run_id": a["run_id"], "session_id": "conv-r"})
        _, rv = await call(s, "review_selection", {"session_id": "conv-r"})
        assert rv["verdict"] == "pass" and rv["run_id"] == sel["run_id"] and rv["issues"] == []
        assert rv["selected"] == {"n_demos": 150, "total_frames": 21833}
        assert rv["training_plan"]["n_sets"] == 5
        assert rv["training_plan"]["num_epochs"] == 400 and rv["training_plan"]["algo"] == "bc_rnn"  # 승인 화면 문구용
        assert "demo_" not in json.dumps(rv) and "better" not in json.dumps(rv)
        # 같은 결과를 두 번 검수하지 않는다
        _, again = await call(s, "review_selection", {"session_id": "conv-r"})
        assert again["verdict"] == "none"
        # 파일을 조작해 예산을 넘기면 revise로 잡는다 (에이전트 보고가 아니라 파일 기준)
        path = isolated / "runs" / sel["run_id"] / "selection.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["selected_ids"] = data["selected_ids"] + data["selected_ids"][:5]
        path.write_text(json.dumps(data), encoding="utf-8")
        _, bad = await call(s, "review_selection", {"run_id": sel["run_id"], "session_id": "conv-r"})
    checks = {i["check"] for i in bad["issues"]}
    assert bad["verdict"] == "revise" and {"budget", "duplicate", "allocation"} <= checks
    assert any(e.get("event") == "review" for e in events(isolated))
