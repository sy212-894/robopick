"""select_demos 검증 테스트. 실제 데이터 파일이 없으면 건너뛴다.

실행: python -m pytest tests -q
"""
import json
import os
from pathlib import Path

import h5py
import pytest

from curation_tools import analyze as A
from curation_tools import select_demos as S

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음")


@pytest.fixture(scope="module")
def analysis():
    return {"run_id": "R-test", **A.analyze(DATA, grid=3)}


@pytest.fixture(scope="module")
def result(analysis):
    return S.select(analysis, budget=150, seed=0)


def test_budget_and_rules(result, analysis):
    by_id = {d["id"]: d for d in analysis["demos"]}
    ids = result["selected_ids"]
    assert len(ids) == 150 and len(set(ids)) == 150
    assert all(by_id[i]["split"] == "train" for i in ids)  # valid가 섞이면 안 된다
    assert result["checks"]["verdict"] == "pass"


def test_allocation_proportional(result):
    alloc = result["allocation"]
    assert sum(a["selected"] for a in alloc) == 150
    assert sum(a["available"] for a in alloc) == 270
    for a in alloc:  # 칸 크기 비율에서 1개 넘게 벗어나지 않는다
        assert abs(a["planned"] - 150 * a["available"] / 270) < 1
        assert a["shortage"] == 0


def test_baselines(result):
    sets = result["sets"]
    assert sets["random_150"]["n_demos"] == 150
    target = sets["curated_150"]["total_frames"]
    assert abs(sets["random_frames"]["total_frames"] - target) <= target * S.FRAME_TOLERANCE


def test_reproducible(analysis, result):
    again = S.select(analysis, budget=150, seed=0)
    assert all(again["sets"][k]["ids"] == v["ids"] for k, v in result["sets"].items())


def test_selection_ignores_labels(analysis, result):
    # 숙련도 라벨을 지워도 같은 결과가 나와야 한다 (라벨은 선별에 쓰지 않는다)
    stripped = {**analysis, "demos": [{k: v for k, v in d.items() if k not in ("quality", "operator")}
                                      for d in analysis["demos"]]}
    assert S.select(stripped, budget=150, seed=0)["selected_ids"] == result["selected_ids"]


def test_outputs(tmp_path, analysis):
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    out = S.run(path, out_root=tmp_path, run_id="R-sel")
    full = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    summary_text = (out / "selection_summary.json").read_text(encoding="utf-8")
    assert "demo_" not in summary_text  # LLM 요약에는 ID 목록이 없어야 한다
    assert "worse" not in summary_text and "better" not in summary_text
    with h5py.File(out / "can_mh_curated.hdf5", "r") as f:
        for name, s in full["sets"].items():
            assert [x.decode() for x in f[f"mask/{name}"][()]] == s["ids"]
        assert len(f["mask/train"]) == 270  # 원래 필터 키는 그대로
    with h5py.File(DATA, "r") as f:
        assert "mask/curated_150" not in f  # 원본은 건드리지 않는다
