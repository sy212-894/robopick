"""train_evaluate 테스트: 학습 계획 생성, 결과 비교표, 1주차 기준 판정, 재사용. 학습은 가짜 결과로 대신한다.

실행: python -m pytest tests -q
"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from curation_tools import server as srv
from curation_tools import train_eval as T

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = [pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음"), pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(srv, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(srv, "DATASETS", {"can_mh": DATA})
    monkeypatch.setattr(T, "RESULTS_STORE", tmp_path / "store")
    return tmp_path


async def call(s, name, args):
    res = await s.call_tool(name, args)
    assert not res.isError, res.content
    return json.loads(res.content[0].text)


def fake_results(plan: dict, rates: dict, n: int = 50) -> dict:
    return {"fingerprint": plan["fingerprint"], "config": plan["config"], "finished_at": "2026-10-12T10:00:00",
            "sets": {k: {"success": round(r * n), "rollouts": n, "train_sec": 600} for k, r in rates.items()}}


async def test_prepare_and_collect(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        a = await call(s, "analyze_data", {"session_id": "c"})
        await call(s, "select_demos", {"analysis_run_id": a["run_id"], "session_id": "c"})
        # 검수 pass 전에는 prepare 대상이 없다
        none = await call(s, "train_evaluate", {"stage": "prepare", "session_id": "c"})
        assert none["status"] == "no_target"
        await call(s, "review_selection", {"session_id": "c"})
        p = await call(s, "train_evaluate", {"stage": "prepare", "session_id": "c"})
        assert p["status"] == "prepared" and p["n_sets"] == 5
        assert p["order"][0].startswith("curated") and p["order"][-1] == "train"
        assert p["sets"]["train"] == 270 and "demo_" not in json.dumps(p)
        not_yet = await call(s, "train_evaluate", {"stage": "collect", "session_id": "c"})
        assert not_yet["status"] == "not_trained"

        plan = json.loads((isolated / "runs" / p["run_id"] / "plan" / "plan.json").read_text(encoding="utf-8"))
        rates = {"curated_150": 0.80, "random_150": 0.50, "stratified_random_150": 0.56,
                 "random_frames": 0.46, "train": 0.84}
        res_dir = isolated / "runs" / p["run_id"] / "results"
        res_dir.mkdir()
        (res_dir / "results.json").write_text(json.dumps(fake_results(plan, rates)), encoding="utf-8")
        out = await call(s, "train_evaluate", {"stage": "collect", "session_id": "c"})
    assert out["status"] == "complete" and not out["reused"]
    j = out["judgement"]
    assert j["gain_vs_random"]["verdict"] == "차이 있음 (높음)" and j["gain_vs_random"]["meets_target_point"]
    assert j["drop_vs_full"]["meets_target_point"] and not j["drop_vs_full"]["confirmed"]  # 롤아웃 50회로는 5%p 이내 확정 불가
    assert j["effect_quality"]["verdict"] == "차이 있음 (높음)"
    assert "validity" not in j and out["label"].startswith("예비 결과")
    row = next(r for r in out["table"] if r["set"] == "curated_150")
    assert row["success_rate"] == 0.8 and row["ci95"][0] < 0.8 < row["ci95"][1]


def test_small_difference_is_inconclusive():
    a, b = {"success": 36, "rollouts": 50}, {"success": 33, "rollouts": 50}  # 72% vs 66%
    assert T.diff(a, b)["verdict"] == "구분 불가"


def test_reuse_and_validity(isolated, tmp_path):
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    runs = isolated / "runs"
    A.run(DATA, out_root=runs, run_id="R-a")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s1")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s2")
    p1 = T.prepare(runs / "R-s1", runs)
    p2 = T.prepare(runs / "R-s2", runs)
    assert p1["fingerprint"] == p2["fingerprint"]  # 같은 선별·설정이면 같은 지문
    plan = json.loads((runs / "R-s1" / "plan" / "plan.json").read_text(encoding="utf-8"))
    bad = fake_results(plan, {"curated_150": 0.1, "random_150": 0.1, "train": 0.1})
    f = tmp_path / "r.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    T.store_results(f)
    out = T.collect(runs / "R-s2")  # 다른 run이지만 지문이 같아 저장된 결과를 재사용
    assert out["reused"] and out["status"] == "partial"
    assert out["judgement"]["validity"].startswith("판정 불가")
    wrong = dict(bad, fingerprint="0000")
    (runs / "R-s1" / "results").mkdir()
    (runs / "R-s1" / "results" / "results.json").write_text(json.dumps(wrong), encoding="utf-8")
    with pytest.raises(ValueError):
        T.collect(runs / "R-s1")
