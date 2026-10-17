"""analyze_data 검증 테스트. 실제 데이터 파일이 없으면 건너뛴다.

실행: python -m pytest tests -q
"""
import json
import os
from pathlib import Path

import pytest

from curation_tools import analyze as A

DATA = Path(os.environ.get("CURATION_DATA", "C:/curation-data/raw/can_mh_low_dim.hdf5"))
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="데이터 파일 없음")


@pytest.fixture(scope="module")
def result():
    return A.analyze(DATA, grid=3)


def test_counts_match_official_script(result):
    # 공식 get_dataset_info.py 결과: 300개, 62,756 프레임, 길이 평균 209.19 / 최소 98 / 최대 1050
    lengths = [d["length"] for d in result["demos"]]
    assert result["dataset"]["n_demos"] == 300
    assert result["dataset"]["total_frames"] == 62756
    assert (min(lengths), max(lengths)) == (98, 1050)
    assert abs(sum(lengths) / len(lengths) - 209.19) < 0.01


def test_quality_labels(result):
    for q in A.QUALITY_LEVELS:
        assert sum(d.get("quality") == q for d in result["demos"]) == 100
    assert all(d.get("split") in ("train", "valid") for d in result["demos"])


def test_conditions_cover_all_demos(result):
    conds = result["conditions"]
    assert len(conds) == 9
    assert sum(c["count"] for c in conds) == 300
    assert sum(c["total_frames"] for c in conds) == 62756
    assert all(c["count"] > 0 for c in conds)


def test_summary_has_no_labels_or_demo_list(tmp_path):
    out = A.run(DATA, out_root=tmp_path, run_id="R-test")
    summary = json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))
    text = json.dumps(summary)
    assert "demos" not in summary
    assert "worse" not in text and "better" not in text  # LLM에 넘기는 요약에는 숙련도 라벨이 없어야 한다
    assert summary["quality_signals"] == ["length", "idle_ratio", "path_length", "gripper_switches"]  # 선별에 실제로 쓰는 신호만
    assert (out / "initial_positions.png").stat().st_size > 0


def test_spearman_basic():
    assert A.spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert A.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
