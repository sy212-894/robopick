"""학습 키트 노트북 테스트: 계획이 노트북에 그대로 들어가는지."""
import json
import os
from pathlib import Path

import pytest

from curation_tools import kit as K
from curation_tools import train_eval as T

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음")


def test_notebook_has_plan_and_jobs(tmp_path, monkeypatch):
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    monkeypatch.setattr(T, "RESULTS_STORE", tmp_path / "store")
    runs = tmp_path / "runs"
    A.run(DATA, out_root=runs, run_id="R-a")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s1", write_hdf5=False)
    T.prepare(runs / "R-s1", runs)
    plan = json.loads((runs / "R-s1" / "plan" / "plan.json").read_text(encoding="utf-8"))
    jobs = K.default_jobs(plan)
    nb = K.build_notebook(plan, jobs)
    src = "\n".join("".join(c["source"]) for c in nb["cells"])
    assert T.compact_plan(plan) in src and repr(jobs[0]) in src
    assert len(jobs) == len(plan["order"]) and all(s == 1 for _, s in jobs)
    # 대신 학습용으로 넣었던 세션 번호·실행별 결과 출력은 없다
    assert "SESSION" not in src and "RUNJSON" not in src
