"""학습 키트와 결과 판정 테스트. 실제 학습 대신 키트 노트북과 같은 형식의 가짜 결과 파일을 쓴다."""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from curation_tools import judge as J
from curation_tools import kit as K
from curation_tools import server as srv
from curation_tools import train_eval as T

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = [pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음"), pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(srv, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(srv, "RESULT_UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(T, "RESULTS_STORE", tmp_path / "store")
    (tmp_path / "uploads").mkdir()
    return tmp_path


async def call(s, name, args):
    res = await s.call_tool(name, args)
    return res, json.loads(res.content[0].text) if res.content else None


def fake_results(plan: dict, rates: dict[str, float], seeds=(1,)) -> dict:
    """키트 노트북(s7)이 만드는 결과 파일 형식. rates: 묶음 → 성공 비율 (시험 100개, 앞에서부터 성공)."""
    final, early = str(plan["config"]["num_epochs"]), str(plan["config"]["early_eval_epoch"])
    runs = {}
    for s in seeds:
        for name, p in rates.items():
            o = [1] * round(p * 100) + [0] * (100 - round(p * 100))
            runs[f"{name}|seed{s}"] = {"set": name, "seed": s, "success": sum(o), "rollouts": 100,
                                       "by_epoch": {early: {"success": 10, "rollouts": 30, "outcomes": [1] * 10 + [0] * 20},
                                                    final: {"success": sum(o), "rollouts": 100, "outcomes": o}}}
    return {"fingerprint": plan["fingerprint"], "run_id": plan["run_id"], "dataset": plan["dataset"]["name"], "mode": "main",
            "platform": "colab", "kit": "compare", "eval_seed": 12345, "policy_seed": "EVAL_SEED+i", "config": plan["config"], "runs": runs}


async def test_kit_then_judge(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        await call(s, "analyze_data", {"session_id": "k"})
        await call(s, "select_demos", {"budget": 150, "session_id": "k"})
        _, rv = await call(s, "review_selection", {"session_id": "k"})
        assert rv["verdict"] == "pass"
        res, kit = await call(s, "build_kit", {"session_id": "k"})
        assert not res.isError and kit["status"] == "ok"
        run_dir = isolated / "runs" / kit["run_id"]
        for f in ("train_curated.ipynb", "train_compare.ipynb", "train_settings.json", "README.txt", "kit.json"):
            assert (run_dir / "kit" / f).exists(), f
        assert kit["data_file"]["file"] == "can_mh_curated.hdf5" and kit["data_file"]["exists"]
        plan = json.loads((run_dir / "plan" / "plan.json").read_text(encoding="utf-8"))

        # 노트북: 환경 판단 셀, 계획, 비교 학습은 선별·무작위·전체 3개, 선별 학습은 1개
        cmp_src = "".join("".join(c["source"]) for c in json.loads((run_dir / "kit" / "train_compare.ipynb").read_text(encoding="utf-8"))["cells"])
        cur_src = "".join("".join(c["source"]) for c in json.loads((run_dir / "kit" / "train_curated.ipynb").read_text(encoding="utf-8"))["cells"])
        assert "google.colab" in cmp_src and "/kaggle" in cmp_src and T.compact_plan(plan) in cmp_src
        assert "('curated_150', 1), ('random_150', 1), ('train', 1)" in cmp_src and "JOBS = [('curated_150', 1)]" in cur_src
        assert "{200: 30, 400: 100}" in cmp_src and "SESSION" not in cmp_src

        # 비교 학습 결과 → 선별 효과 판정
        (isolated / "uploads" / "r_compare.json").write_text(
            json.dumps(fake_results(plan, {"curated_150": 0.8, "random_150": 0.6, "train": 0.78})), encoding="utf-8")
        res, eff = await call(s, "judge_results", {"file_name": "r_compare.json", "session_id": "k"})
        assert not res.isError and eff["kind"] == "effect" and eff["title"] == "선별 효과 판정"
        assert eff["gain_vs_random"]["diff"] == pytest.approx(0.2) and eff["drop_vs_full"]["confirmed"] is True
        assert "시드 1개" in eff["note"]

        # 선별만 학습한 결과 → 결과 확인 (판정하지 않음)
        (isolated / "uploads" / "r_curated.json").write_text(json.dumps(fake_results(plan, {"curated_150": 0.83})), encoding="utf-8")
        _, chk = await call(s, "judge_results", {"file_name": "r_curated.json", "session_id": "k"})
        assert chk["kind"] == "check" and "gain_vs_random" not in chk and chk["rates"]["curated"]["rate"] == 0.83

        # 파일 이름 없이 부르면 이 대화의 최근 판정
        _, last = await call(s, "judge_results", {"session_id": "k"})
        assert last["kind"] == "check"

        # 우리 실험 결과(results.json)는 만들지도 덮어쓰지도 않는다
        assert not (run_dir / "results" / "results.json").exists()
        assert len(list((run_dir / "results" / "uploaded").glob("*_judgement.json"))) == 2


@pytest.mark.parametrize("change,msg", [({"fingerprint": "x"}, "지문"), ({"eval_seed": 1}, "난수"), ({"run_id": "../x"}, "계획"),
                                        ({"mode": "pilot"}, "mode")])
async def test_judge_rejects(isolated, change, msg):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        await call(s, "analyze_data", {"session_id": "j"})
        await call(s, "select_demos", {"budget": 150, "session_id": "j"})
        await call(s, "review_selection", {"session_id": "j"})
        _, kit = await call(s, "build_kit", {"session_id": "j"})
    plan = json.loads((isolated / "runs" / kit["run_id"] / "plan" / "plan.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match=msg):
        J.judge({**fake_results(plan, {"curated_150": 0.8}), **change}, isolated / "runs")


async def test_judge_bad_file_name(isolated):
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        for name in ("../x.json", "a.txt", "none.json"):
            res = await s.call_tool("judge_results", {"file_name": name, "session_id": "b"})
            assert res.isError


def test_notebook_without_original_needs_kit_file():
    plan = {"fingerprint": "f", "run_id": "R-x", "dataset": {"name": "my_data", "hf_path": None},
            "config": dict(T.TRAIN_CONFIG), "order": ["curated_100", "random_100", "train"],
            "sets": {"curated_100": ["demo_1"], "random_100": ["demo_2"], "train": ["demo_1", "demo_2"]}}
    src = "".join("".join(c["source"]) for c in K.build_notebook(plan, K.kit_jobs(plan, "curated"))["cells"])
    assert "my_data_curated.hdf5" in src and "SystemExit" in src
