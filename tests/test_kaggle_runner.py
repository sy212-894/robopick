"""kaggle_runner 테스트: Kaggle에 접속하지 않고 가짜 도우미로 launch / status / stop / resume과 안전장치를 확인한다.

실행: python -m pytest tests -q
"""
import json
import os
from pathlib import Path

import pytest

from curation_tools import kaggle_runner as K
from curation_tools import train_eval as T

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음")


class FakeKaggle:
    """kaggle_helper 대신 응답한다. 호출 기록을 남긴다."""

    def __init__(self):
        self.calls, self.state, self.used = [], "RUNNING", 10.0
        self.lines: list[str] = []
        self.results: dict | None = None

    def __call__(self, cmd, **a):
        self.calls.append((cmd, a))
        if cmd == "quota":
            return {"gpu_used_hours": self.used, "refresh": "2026-10-17T00:00:00Z"}
        if cmd == "push":
            return {"ref": "x", "url": "https://www.kaggle.com/code/u/x", "version": 1, "error": None}
        if cmd == "status":
            return {"status": f"KernelWorkerStatus.{self.state}", "failure": None}
        if cmd == "logs":
            return {"lines": self.lines, "live": True}
        if cmd == "cancel":
            self.state = "CANCEL_ACKNOWLEDGED"
            return {"error": None}
        if cmd == "output":
            dest = Path(a["dest"]) / "run"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"results_main_{self.results['fingerprint']}.json").write_text(json.dumps(self.results), encoding="utf-8")
            return {}
        raise AssertionError(cmd)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    monkeypatch.setattr(T, "RESULTS_STORE", tmp_path / "store")
    runs = tmp_path / "runs"
    A.run(DATA, out_root=runs, run_id="R-a")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s1", write_hdf5=False)
    T.prepare(runs / "R-s1", runs)
    fake = FakeKaggle()
    monkeypatch.setattr(K, "run_helper", fake)
    monkeypatch.setattr(K, "LAUNCH_ENABLED", True)
    return runs, fake


def _run(plan, key, ok):
    name, seed = key.split("|seed")
    o = [1] * ok + [0] * (50 - ok)
    return {"set": name, "seed": int(seed), "success": ok, "rollouts": 50, "train_sec": 600, "eval_sec": 700,
            "by_epoch": {"200": {"success": 10, "rollouts": 30, "outcomes": [1] * 10 + [0] * 20}, "400": {"success": ok, "rollouts": 50, "outcomes": o}}}


def test_notebook_has_session_runjson_and_resume(env):
    runs, _ = env
    plan = json.loads((runs / "R-s1" / "plan" / "plan.json").read_text(encoding="utf-8"))
    jobs = K.default_jobs(plan)
    nb = K.build_notebook(plan, jobs, {"curated_150|seed1": {"set": "curated_150"}})
    src = "\n".join("".join(c["source"]) for c in nb["cells"])
    assert "print('SESSION'" in src and "RUNJSON" in src
    assert plan["fingerprint"] in "".join(nb["cells"][3]["source"]) or "PLAN_B64" in src
    assert "curated_150|seed1" in src          # 이어서 학습할 끝난 실행
    assert len(jobs) == len(plan["order"]) and all(s == 1 for _, s in jobs)


def test_launch_status_stop_resume(env):
    runs, fake = env
    d = runs / "R-s1"
    r = K.launch(d, runs)
    assert r["status"] == "launched" and r["jobs"] == 5
    assert K.launch(d, runs)["status"] == "already_running"
    # 실행 중: 로그에서 세션 번호와 끝난 실행 1개를 읽는다
    plan = json.loads((d / "plan" / "plan.json").read_text(encoding="utf-8"))
    fake.lines = ["SESSION 123456789", "RUNJSON " + json.dumps({"curated_150|seed1": _run(plan, "curated_150|seed1", 45)})]
    s = K.status(d, runs)
    assert s["status"] == "running" and s["done_runs"] == 1 and s["can_stop"]
    # 중단: 이 실행의 세션 번호로만
    assert K.stop(d, runs)["status"] == "stopping"
    assert ("cancel", {"session_id": 123456789}) in fake.calls
    s = K.status(d, runs)
    assert s["status"] == "stopped" and s["can_resume"]
    # 이어서: 끝난 1개를 넣어 다시 올리고, 남은 4개만 예상 시간에 넣는다
    fake.state = "RUNNING"
    r = K.resume(d, runs)
    assert r["status"] == "resumed" and r["left_runs"] == 4
    nb = json.loads((d / "kaggle" / "push" / "run.ipynb").read_text(encoding="utf-8"))
    assert "curated_150|seed1" in "".join("".join(c["source"]) for c in nb["cells"])


def test_complete_ingests_results(env):
    runs, fake = env
    d = runs / "R-s1"
    K.launch(d, runs)
    plan = json.loads((d / "plan" / "plan.json").read_text(encoding="utf-8"))
    fake.results = {"fingerprint": plan["fingerprint"], "run_id": "R-s1", "mode": "main", "config": plan["config"],
                    "runs": {f"{n}|seed1": _run(plan, f"{n}|seed1", 30 + i) for i, n in enumerate(plan["order"])}}
    fake.state = "COMPLETE"
    s = K.status(d, runs)
    assert s["status"] == "complete"
    assert T.collect(d)["status"] == "complete"
    assert K.launch(d, runs)["status"] == "already_trained"


def test_guards(env, tmp_path):
    runs, fake = env
    d = runs / "R-s1"
    fake.used = 29.5   # 남은 GPU 0.5시간 < 예상 110분
    assert K.launch(d, runs)["status"] == "no_gpu"
    fake.used = 10.0
    # 다른 실행 폴더에서 학습이 돌고 있으면 시작하지 않는다
    other = runs / "R-other" / "kaggle"
    other.mkdir(parents=True)
    (other / "state.json").write_text(json.dumps({"slug": "u/curation-run-x", "status": "running"}), encoding="utf-8")
    assert K.launch(d, runs)["status"] == "busy"
    # 이 도구가 올리지 않은 노트북은 멈추지 않는다
    (other / "state.json").unlink()
    K.launch(d, runs)
    st = K.load_state(d)
    st.update(slug="qkdsy482/curation-seeds45", session_id=1)
    K._save_state(d, st)
    with pytest.raises(ValueError):
        K.stop(d, runs)


def test_launch_disabled_by_default(env, monkeypatch):
    runs, fake = env
    monkeypatch.setattr(K, "LAUNCH_ENABLED", False)
    assert K.launch(runs / "R-s1", runs)["status"] == "disabled"
    assert not any(c == "push" for c, _ in fake.calls)   # 꺼져 있으면 Kaggle에 올리지 않는다


def test_status_before_launch(env):
    runs, fake = env
    d = runs / "R-s1"
    assert K.status(d, runs)["status"] == "not_launched"      # 결과도 없고 올린 적도 없음
    assert not fake.calls                                       # Kaggle에 묻지 않는다
