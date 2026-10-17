"""근거표 추천 규칙 테스트 (실험 파일 없이 가짜 근거표로)."""
from curation_tools import evidence as E


def _row(ds, b, gain_verdict, drop_hi, gain_diff=0.1):
    return {"dataset": ds, "budget": b, "experiment": f"{ds} {b}",
            "gain_vs_random": {"diff": gain_diff, "ci95": [0.0, 0.2], "verdict": gain_verdict},
            "drop_vs_full": {"diff": 0.0, "ci95": [-0.1, drop_hi], "verdict": "구분 불가", "confirmed": drop_hi <= 0.05}}


DOC = {"rows": [_row("can_mh", 60, "차이 있음 (높음)", 0.089), _row("can_mh", 135, "구분 불가", -0.069),
                _row("can_mh", 150, "구분 불가", 0.039), _row("square_mh", 150, "차이 있음 (높음)", 0.08),
                _row("lift_mh", 100, "구분 불가", 0.2)]}


def test_recommend_rule_order():
    # 1. 하락 기준이 확인된 가장 작은 개수 (150도 확인됐지만 135가 더 작다)
    assert E.recommend("can_mh", DOC)["budget"] == 135
    # 2. 하락 기준 확인이 없으면 무작위보다 높다고 확인된 개수
    r = E.recommend("square_mh", DOC)
    assert r["budget"] == 150 and r["basis"] == "gain_vs_random"
    # 3. 둘 다 없으면 추천하지 않는다
    assert E.recommend("lift_mh", DOC)["budget"] is None
    assert E.recommend("transport_mh", DOC)["budget"] is None


def test_lookup_nearest():
    assert E.lookup("can_mh", 135, DOC)["status"] == "tested"
    x = E.lookup("can_mh", 100, DOC)
    assert x["status"] == "not_tested" and [r["budget"] for r in x["rows"]] == [60, 135]
    assert [r["budget"] for r in E.lookup("can_mh", 200, DOC)["rows"]] == [150]
    assert E.lookup("transport_mh", 100, DOC)["status"] == "no_evidence"


def test_saved_table_matches_rule():
    # 저장된 근거표로도 규칙이 돌아간다 (Can 135, Square 150)
    doc = E.load()
    assert E.recommend("can_mh", doc)["budget"] == 135
    assert E.recommend("square_mh", doc)["budget"] == 150
