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


def test_early_eval_judgement():
    plan = {"order": ["curated_150", "random_150"], "sets": {"curated_150": ["demo_1"] * 150, "random_150": ["demo_2"] * 150},
            "config": {"early_eval_epoch": 200}}
    res = {"sets": {"curated_150": {"success": 45, "rollouts": 50, "by_epoch": {"200": {"success": 21, "rollouts": 30}}},
                    "random_150": {"success": 40, "rollouts": 50, "by_epoch": {"200": {"success": 9, "rollouts": 30}}}}}
    out = T.compare(plan, res)
    assert out["judgement"]["early_gain_vs_random"]["verdict"] == "차이 있음 (높음)"  # 70% vs 30%
    assert out["judgement"]["gain_vs_random"]["verdict"] == "구분 불가"              # 90% vs 80%
    assert out["table"][0]["early"]["success_rate"] == 0.7


def _seed_doc(fp, runs, mode="seeds", config=None):
    cfg = dict(config or {"early_eval_epoch": 200})
    return {"fingerprint": fp, "run_id": "R-s1", "mode": mode, "config": cfg,
            "runs": {f"{k}|seed{s}": {"set": k, "seed": s, "success": v, "rollouts": 50,
                                      "by_epoch": {"200": {"success": v // 2, "rollouts": 30}}}
                     for (k, s), v in runs.items()}}


def test_multi_seed_requires_same_direction():
    plan = {"order": ["curated_150", "random_150"], "sets": {"curated_150": ["demo_1"] * 150, "random_150": ["demo_2"] * 150},
            "config": {"early_eval_epoch": 200}}
    base = {"config": {"seed": 1}, "sets": {"curated_150": {"success": 47, "rollouts": 50}, "random_150": {"success": 40, "rollouts": 50}}}
    same = _seed_doc("x", {("curated_150", 2): 46, ("random_150", 2): 39, ("curated_150", 3): 45, ("random_150", 3): 38})
    out = T.compare(plan, base, same)
    g = out["judgement"]["gain_vs_random"]
    assert g["n_seeds"] == 3 and g["verdict"] == "차이 있음 (높음)" and all(v > 0 for v in g["per_seed_diff"].values())
    row = out["table"][0]
    assert row["n_seeds"] == 3 and row["rollouts"] == 150 and row["success"] == 138 and len(row["per_seed"]) == 3
    assert out["label"].startswith("시드 3개")
    # 합친 신뢰구간은 0보다 커도, 한 시드에서 무작위가 이기면 구분 불가
    mixed = _seed_doc("x", {("curated_150", 2): 50, ("random_150", 2): 38, ("curated_150", 3): 40, ("random_150", 3): 42})
    g2 = T.compare(plan, base, mixed)["judgement"]["gain_vs_random"]
    assert g2["ci95"][0] > 0 and g2["verdict"] == "구분 불가" and "방향" in g2["note"]


def test_save_seed_results_checks(isolated, tmp_path):
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    runs = isolated / "runs"
    A.run(DATA, out_root=runs, run_id="R-a")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s1")
    p = T.prepare(runs / "R-s1", runs)
    plan = json.loads((runs / "R-s1" / "plan" / "plan.json").read_text(encoding="utf-8"))
    f = tmp_path / "seeds.json"
    ok = _seed_doc(p["fingerprint"], {("curated_150", 2): 45, ("random_150", 2): 40}, config=dict(plan["config"], seed=2))
    for bad in (dict(ok, mode="smoke"), dict(ok, fingerprint="0000"),
                dict(ok, config=dict(plan["config"], num_epochs=2)),
                _seed_doc(p["fingerprint"], {("curated_150", 1): 45}, config=plan["config"])):
        f.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            T.save_seed_results(f, runs)
    f.write_text(json.dumps(ok), encoding="utf-8")
    T.save_seed_results(f, runs)
    (runs / "R-s1" / "results").mkdir(exist_ok=True)
    (runs / "R-s1" / "results" / "results.json").write_text(json.dumps(fake_results(plan, {"curated_150": 0.94, "random_150": 0.8, "train": 0.96})), encoding="utf-8")
    out = T.collect(runs / "R-s1")
    row = next(r for r in out["table"] if r["set"] == "curated_150")
    assert row["n_seeds"] == 2 and row["rollouts"] == 100
    assert "시드 수가 다름" in out["label"]  # train 등은 시드 1개뿐


SQUARE = Path(os.environ.get("CURATION_SQUARE", "C:/curation-data/raw/square_mh_low_dim.hdf5"))


@pytest.mark.skipif(not SQUARE.exists(), reason="Square 데이터 없음")
def test_square_plan(tmp_path):
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    import base64, zlib
    runs = tmp_path / "runs"
    a = A.run(SQUARE, out_root=runs, run_id="R-sq-a")
    an = json.loads((a / "analysis.json").read_text(encoding="utf-8"))
    assert an["dataset"]["name"] == "square_mh" and an["dataset"]["object"] == "너트"
    s = S.run(a / "analysis.json", out_root=runs, run_id="R-sq-s")
    assert (s / "square_mh_curated.hdf5").exists()
    p = T.prepare(s, runs)
    assert p["dataset"] == "square_mh" and p["n_sets"] == 5
    assert p["config"]["num_epochs"] == 600 and p["config"]["early_eval_epoch"] == 400  # 파일럿(6-4) 결과로 늘림
    assert p["notebook"] == "kaggle/03_square.ipynb" and p["est_minutes"] == 5 * 27
    body = json.loads(zlib.decompress(base64.b64decode((s / "plan" / "plan_b64.txt").read_text())))
    assert body["hf_path"] == "v1.5/square/mh/low_dim_v15.hdf5" and body["dataset"] == "square_mh"


def _paired_doc(outcomes: dict) -> dict:
    return {"epoch": 400, "runs": {f"{k}|seed{s}": {"set": k, "seed": s, "outcomes": o, "success": sum(o)}
                                   for (k, s), o in outcomes.items()}}


def test_paired_narrower_than_unpaired():
    # 같은 위치에서 대부분 함께 성공·실패하고, 선별만 성공한 위치가 조금 있는 경우: 짝지으면 신뢰구간이 좁아진다
    base = [1] * 35 + [0] * 15
    cur = [1] * 35 + [1] * 4 + [0] * 11   # 무작위가 실패한 위치 중 4곳에서 선별만 성공
    doc = _paired_doc({("curated_150", s): cur for s in (1, 2, 3)} | {("random_150", s): base for s in (1, 2, 3)})
    p = T.paired_diff(doc, "curated_150", "random_150")
    u = T.diff({"success": 3 * sum(cur), "rollouts": 150}, {"success": 3 * sum(base), "rollouts": 150})
    assert p["diff"] == u["diff"] == 0.08
    assert p["ci95"][1] - p["ci95"][0] < u["ci95"][1] - u["ci95"][0]
    assert p["verdict"] == "차이 있음 (높음)" and u["verdict"] == "구분 불가"
    assert p["pairs"] == {"a_only": 12, "b_only": 0, "both": 105, "neither": 33}


def test_paired_requires_same_direction():
    a, b = [1] * 30 + [0] * 20, [1] * 20 + [0] * 30
    doc = _paired_doc({("curated_150", 1): a, ("random_150", 1): b, ("curated_150", 2): a, ("random_150", 2): b,
                       ("curated_150", 3): b, ("random_150", 3): [1] * 22 + [0] * 28})
    p = T.paired_diff(doc, "curated_150", "random_150")
    assert p["ci95"][0] > 0 and p["per_seed_diff"][3] < 0
    assert p["verdict"] == "구분 불가" and "방향" in p["note"]


def _square_doc(outcomes: dict) -> dict:
    """Square 노트북 형식: 모든 시드가 runs에, 시범별 결과는 by_epoch 안에."""
    runs = {}
    for (name, seed), by in outcomes.items():
        last = by[600]
        runs[f"{name}|seed{seed}"] = {"set": name, "seed": seed, "success": sum(last), "rollouts": len(last), "train_sec": 700,
                                      "finished_at": f"2026-10-13T0{seed}:00:00+09:00",
                                      "by_epoch": {str(e): {"success": sum(o), "rollouts": len(o), "outcomes": o} for e, o in by.items()}}
    return {"fingerprint": "fp", "mode": "main", "config": {"num_epochs": 600, "early_eval_epoch": 400, "seed": 1}, "runs": runs}


def test_square_format_compare_paired():
    plan = {"config": {"num_epochs": 600, "early_eval_epoch": 400, "seed": 1},
            "order": ["curated_150", "random_150", "train"],
            "sets": {"curated_150": ["d"] * 150, "random_150": ["d"] * 150, "train": ["d"] * 270}}
    hi, lo = [1] * 30 + [0] * 20, [1] * 20 + [0] * 30
    early_hi, early_lo = [1] * 10 + [0] * 20, [0] * 30
    doc = _square_doc({**{("curated_150", s): {400: early_hi, 600: hi} for s in (1, 2, 3)},
                       **{("random_150", s): {400: early_lo, 600: lo} for s in (1, 2, 3)},
                       **{("train", s): {400: early_lo, 600: hi} for s in (1, 2, 3)}})
    out = T.compare(plan, doc)
    row = next(r for r in out["table"] if r["set"] == "curated_150")
    assert row["n_seeds"] == 3 and row["success"] == 90 and row["early"]["epoch"] == 400
    j = out["judgement"]
    assert j["gain_vs_random"]["diff"] == 0.2 and j["paired_gain_vs_random"]["diff"] == 0.2
    assert j["paired_gain_vs_random"]["n_pairs"] == 150 and j["paired_gain_vs_random"]["verdict"] == "차이 있음 (높음)"
    assert j["paired_early_gain_vs_random"]["diff"] == round(10 / 30, 4) and "400 epoch" in j["paired_early_gain_vs_random"]["question"]
    assert j["paired_drop_vs_full"]["diff"] == 0 and j["paired_drop_vs_full"]["verdict"] == "구분 불가"
    # 400·600 epoch 합침: 시드마다 30 + 50 = 80쌍, 선별 40/80 vs 무작위 20/80
    both = j["paired_both_gain_vs_random"]
    assert both["n_pairs"] == 240 and both["diff"] == 0.25 and "400·600" in both["question"]
    assert j["paired_both_drop_vs_full"]["diff"] == round(-10 / 80, 4)


def test_square_pilot_file_has_no_paired_for_missing_sets():
    # 파일럿은 전체·무작위만 있어 선별 비교는 없고, 결과 파일을 그대로 읽을 수 있어야 한다
    f = Path(__file__).parent.parent / "results" / "square_mh_3b6cc7529b7e1101_pilot_kaggle.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    plan = {"config": doc["config"], "order": ["random_150", "train"], "sets": {"random_150": ["d"] * 150, "train": ["d"] * 270}}
    out = T.compare(plan, doc)
    assert {r["set"]: r["success"] for r in out["table"]} == {"random_150": 5, "train": 5}
    assert not any(k.startswith("paired") for k in out["judgement"])
    assert T._outcomes(doc["runs"]["train|seed1"], 400) == [0, 1, 1, 1, 0, 0, 0, 0, 1, 1]


def test_paired_report_five_sets():
    # 1주차 최종 평가: 묶음 5개 x 시드 3개 x 위치 100개. 판정 5개가 모두 나와야 한다
    hi, mid, lo = [1] * 80 + [0] * 20, [1] * 70 + [0] * 30, [1] * 60 + [0] * 40
    sets = {"curated_150": hi, "random_150": lo, "train": mid, "stratified_random_150": mid, "random_frames": lo}
    doc = _paired_doc({(k, s): o for k, o in sets.items() for s in (1, 2, 3)})
    rep = T.paired_report(doc)
    assert "위치 100개" in rep["label"]
    assert {"gain_vs_random", "drop_vs_full", "effect_quality", "effect_allocation", "same_frames"} <= set(rep)
    assert rep["gain_vs_random"]["n_pairs"] == 300 and rep["gain_vs_random"]["diff"] == 0.2
    assert rep["same_frames"]["meaning"].startswith("선별 쪽이 프레임 맞춘 무작위보다 높음")


def test_save_paired_makes_primary_judgement(isolated, tmp_path):
    # 짝지은 재평가를 저장하면 collect가 그것을 주 판정으로 맨 앞에 낸다. 같은 계획의 새 실행 폴더(데모)에서도 저장소에서 찾는다
    from curation_tools import analyze as A
    from curation_tools import select_demos as S
    runs = isolated / "runs"
    A.run(DATA, out_root=runs, run_id="R-a")
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s1")
    p = T.prepare(runs / "R-s1", runs)
    plan = json.loads((runs / "R-s1" / "plan" / "plan.json").read_text(encoding="utf-8"))
    (runs / "R-s1" / "results").mkdir(exist_ok=True)
    res = runs / "R-s1" / "results" / "results.json"
    res.write_text(json.dumps(fake_results(plan, {k: 0.7 for k in plan["sets"]})), encoding="utf-8")
    T.store_results(res)
    hi, lo = [1] * 80 + [0] * 20, [1] * 60 + [0] * 40
    ok = {**_paired_doc({(k, s): (hi if k.startswith("curated") else lo) for k in plan["sets"] for s in (1, 2, 3)}),
          "fingerprint": p["fingerprint"], "run_id": "R-s1", "mode": "paired", "policy_seed": "EVAL_SEED+i"}
    f = tmp_path / "paired.json"
    short = json.loads(json.dumps(ok))
    short["runs"]["train|seed1"]["outcomes"] = lo[:50]
    for bad in (dict(ok, fingerprint="0000"), dict(ok, mode="seeds"), dict(ok, policy_seed=None), short):
        f.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            T.save_paired(f, runs)
    f.write_text(json.dumps(ok), encoding="utf-8")
    T.save_paired(f, runs)
    assert (isolated / "store" / f"{p['fingerprint']}_paired.json").exists()
    # 같은 선별로 새로 만든 실행 폴더 (데모에서 승인할 때마다 생긴다)
    S.run(runs / "R-a" / "analysis.json", out_root=runs, run_id="R-s2")
    T.prepare(runs / "R-s2", runs)
    out = T.collect(runs / "R-s2")
    first = next(iter(out["judgement"]))
    assert first == "paired_gain_vs_random" and out["judgement"][first]["primary"]
    assert out["judgement"][first]["n_pairs"] == 300 and out["judgement"][first]["diff"] == 0.2
    assert out["paired"]["rates"]["train"] == {"success": 180, "rollouts": 300, "seeds": 3}


def test_paired_drop_confirmed_uses_ci_upper():
    # 1주차 "하락 5%p 이내": 짝지은 비교에서도 신뢰구간 위쪽 끝이 5%p 이하일 때만 기준 확정
    hi, mid = [1] * 85 + [0] * 15, [1] * 75 + [0] * 25
    rep = T.paired_report(_paired_doc({**{("curated_135", s): hi for s in (1, 2, 3)}, **{("train", s): mid for s in (1, 2, 3)}}))
    d = rep["drop_vs_full"]
    assert d["diff"] == -0.1 and d["confirmed"] is True
    rep2 = T.paired_report(_paired_doc({**{("curated_135", s): mid for s in (1, 2, 3)}, **{("train", s): hi for s in (1, 2, 3)}}))
    assert rep2["drop_vs_full"]["confirmed"] is False


def test_seeds_report_rule():
    """추가 분석 규칙 (한계 1, cfd710b): 신뢰구간 0 위 + 시드 5개 중 4개 이상 높음. 동점은 세지 않는다. 하락 기준은 시드+위치 신뢰구간."""
    from curation_tools import train_eval as TE

    def doc(per_seed_hits, robust_hi):
        runs = {}
        for s, (c, r, t) in enumerate(per_seed_hits, start=1):
            for name, k in (("curated_150", c), ("random_150", r), ("train", t)):
                runs[f"{name}|seed{s}"] = {"set": name, "seed": s, "success": k, "outcomes": [1] * k + [0] * (100 - k)}
        return {"runs": runs, "robust": {"drop_vs_full": {"ci95_seed_and_position": [-0.3, robust_hi]}}}

    # 시드 2 동점, 나머지 4개 선별이 높음 → 차이 있음
    r = TE.seeds_report(doc([(95, 66, 91), (76, 76, 68), (61, 49, 65), (73, 37, 79), (89, 66, 30)], 0.058))
    g = r["seeds_gain_vs_random"]
    assert g["higher_seeds"] == 4 and g["verdict"] == "차이 있음 (높음)" and g["n_seeds"] == 5
    assert r["seeds_drop_vs_full"]["verdict"] == "하락 기준 미충족" and r["seeds_drop_vs_full"]["ci95"] == [-0.3, 0.058]
    # 높은 시드가 3개뿐이면 신뢰구간이 0 위여도 구분 불가
    r = TE.seeds_report(doc([(95, 66, 90), (76, 76, 90), (61, 61, 90), (73, 37, 90), (89, 66, 90)], 0.04))
    assert r["seeds_gain_vs_random"]["higher_seeds"] == 3 and r["seeds_gain_vs_random"]["verdict"] == "구분 불가"
    assert r["seeds_drop_vs_full"]["confirmed"] is True
