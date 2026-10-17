"""근거표와 추천 개수: 지금까지의 학습 실험 결과를 표 하나로 모으고, 몇 개를 고르면 되는지 코드가 추천한다.

사용자는 매번 학습하지 않고 선별 결과를 바로 받는다. 대신 "이 방법으로 고르면 무엇이 확인됐는지"를 이 표로 보여 준다.
- 근거표(results/evidence.json): 데이터·개수별 주 판정(같은 위치 짝지은 비교)과, 있으면 추가 분석(학습 시드를 늘린 판정)
- 추천 규칙 (2026-10-17, 예산 60 2차 결과를 보기 전에 커밋):
  1. 전체 데이터 대비 하락 5%p 이내가 주 판정으로 확인된 개수 중 가장 작은 개수 (적게 모아도 전체와 비슷)
  2. 없으면 선별이 무작위보다 높다고 주 판정으로 확인된 개수 중 가장 큰 개수
  3. 둘 다 없으면 추천하지 않는다 (기본값 150을 쓰되 근거 없음을 알린다)
- 요청한 개수가 표에 없으면 바로 아래·위 개수의 결과를 "참고(이 개수는 확인 안 됨)"로 붙인다

하락 기준 "확인"은 1주차 기준 그대로: 짝지은 비교 신뢰구간의 위쪽 끝(전체가 더 높은 쪽)이 +5%p 이하.

근거표 다시 만들기: python -m curation_tools.evidence --build
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from curation_tools import train_eval as T

REPO = Path(__file__).resolve().parent.parent
EVIDENCE_PATH = REPO / "results" / "evidence.json"
RUNS = Path("C:/curation-data/runs")
DEFAULT_BUDGET = 150
RULE = ("전체 대비 하락 5%p 이내가 확인된 가장 작은 개수 → 없으면 무작위보다 높다고 확인된 가장 큰 개수 → 없으면 추천 없음 "
        "(주 판정 기준, 2026-10-17 예산 60 2차 결과 전에 정함)")

# (데이터, 개수, 주 판정 파일, 추가 분석 파일, 실험 이름). 파일은 RUNS 아래 경로. 새 실험을 붙이면 여기에 더한다
SOURCES = [
    ("can_mh", 60, "R-20261013-select-b60/results/results_paired_round1.json", None, "예산 60 1차 (docs/12)"),
    ("can_mh", 135, "R-20261012-select-b135/results/results_paired_combined.json", None, "예산 135 (docs/09)"),
    ("can_mh", 150, "R-20261011-select-main/results/results_paired.json",
     "R-20261011-select-main/results/results_paired_seeds.json", "본 실험 150 (docs/07, 11)"),
    ("square_mh", 150, "R-20261012-square-select", None, "Square 150 (docs/06)"),
]


def _cmp(x: dict | None, drop: bool = False) -> dict | None:
    if not x:
        return None
    out = {"diff": x["diff"], "ci95": x["ci95"], "verdict": x["verdict"], "n_seeds": x.get("n_seeds")}
    if drop:
        out["confirmed"] = x["ci95"][1] <= T.MAX_DROP
    return out


def _row(dataset: str, budget: int, main: str, extra: str | None, name: str, runs: Path) -> dict:
    p = runs / main
    if p.is_dir():  # 짝지은 재평가 파일이 없는 실험(Square)은 collect가 학습 결과로 짝지은 비교를 낸다
        c = T.collect(p)
        j = c["judgement"]
        gain, drop = j.get("paired_gain_vs_random") or j.get("gain_vs_random"), j.get("paired_drop_vs_full") or j.get("drop_vs_full")
        counts = {r["set"]: (r["success"], r["rollouts"]) for r in c.get("table", []) if "success" in r}
    else:
        doc = json.loads(p.read_text(encoding="utf-8-sig"))
        rep = T.paired_report(doc)
        gain, drop = rep.get("gain_vs_random"), rep.get("drop_vs_full")
        counts = {}
        for r in doc["runs"].values():
            k, n = counts.get(r["set"], (0, 0))
            counts[r["set"]] = (k + sum(r["outcomes"]), n + len(r["outcomes"]))
    # 묶음별 성공률 (결과 확인 화면에서 사용자 결과와 나란히 보여 준다). 선별·무작위·전체만
    rates = {}
    for role, pick in (("curated", lambda s: s.startswith("curated")),
                       ("random", lambda s: s.startswith("random_") and s != "random_frames"), ("train", lambda s: s == "train")):
        hit = next((s for s in sorted(counts) if pick(s)), None)
        if hit:
            k, n = counts[hit]
            rates[role] = {"set": hit, "success": k, "rollouts": n, "rate": round(k / n, 4), "ci95": list(T.wilson(k, n))}
    row = {"dataset": dataset, "budget": budget, "experiment": name, "source": main, "rates": rates,
           "gain_vs_random": _cmp(gain), "drop_vs_full": _cmp(drop, drop=True)}
    if extra and (runs / extra).exists():
        s = T.seeds_report(json.loads((runs / extra).read_text(encoding="utf-8")))
        g, d = s["seeds_gain_vs_random"], s["seeds_drop_vs_full"]
        row["extra"] = {"label": s["label"], "source": extra,
                        "gain_vs_random": {**_cmp(g), "note": g["note"]},
                        "drop_vs_full": {**_cmp(d), "confirmed": d["confirmed"], "note": d["note"]}}
    return row


def build(runs: Path = RUNS, path: Path = EVIDENCE_PATH) -> dict:
    rows = [_row(*s, runs=runs) for s in SOURCES]
    doc = {"built_at": dt.datetime.now().isoformat(timespec="seconds"), "rule": RULE, "max_drop": T.MAX_DROP, "rows": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def load(path: Path = EVIDENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _gain_ok(r: dict) -> bool:
    return bool(r.get("gain_vs_random")) and r["gain_vs_random"]["verdict"].startswith("차이 있음")


def _drop_ok(r: dict) -> bool:
    return bool(r.get("drop_vs_full")) and r["drop_vs_full"]["confirmed"]


def recommend(dataset: str, doc: dict | None = None) -> dict:
    """미리 정한 규칙으로 추천 개수와 그 근거 행을 돌려준다."""
    rows = [r for r in (doc or load())["rows"] if r["dataset"] == dataset]
    drop = sorted((r for r in rows if _drop_ok(r)), key=lambda r: r["budget"])
    if drop:
        r = drop[0]
        return {"budget": r["budget"], "basis": "drop_vs_full", "row": r,
                "reason": f"{r['budget']}개에서 전체 데이터 대비 하락이 5%p 이내로 확인됨 (신뢰구간 위쪽 끝 "
                          f"{r['drop_vs_full']['ci95'][1] * 100:+.1f}%p, {r['experiment']})"}
    gain = sorted((r for r in rows if _gain_ok(r)), key=lambda r: -r["budget"])
    if gain:
        r = gain[0]
        return {"budget": r["budget"], "basis": "gain_vs_random", "row": r,
                "reason": f"{r['budget']}개에서 선별이 무작위보다 높다고 확인됨 ({r['gain_vs_random']['diff'] * 100:+.1f}%p, "
                          f"{r['experiment']}). 전체 데이터와 비슷한지는 확인되지 않음"}
    return {"budget": None, "basis": None, "row": None,
            "reason": f"이 데이터는 학습 실험 결과가 없어 추천할 개수가 없습니다. 기본값 {DEFAULT_BUDGET}개를 쓰며, 확인된 근거는 없습니다"}


def lookup(dataset: str, budget: int, doc: dict | None = None) -> dict:
    """요청한 개수의 근거. 표에 있으면 확인됨, 없으면 바로 아래·위 개수의 결과를 참고로."""
    rows = sorted((r for r in (doc or load())["rows"] if r["dataset"] == dataset), key=lambda r: r["budget"])
    exact = next((r for r in rows if r["budget"] == budget), None)
    if exact:
        return {"status": "tested", "budget": budget, "rows": [exact]}
    below = [r for r in rows if r["budget"] < budget][-1:]
    above = [r for r in rows if r["budget"] > budget][:1]
    near = below + above
    return {"status": "not_tested" if near else "no_evidence", "budget": budget, "rows": near}


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="근거표를 만들고 추천 개수를 출력한다")
    p.add_argument("--build", action="store_true", help="실험 결과 파일에서 근거표를 다시 만든다")
    p.add_argument("--dataset", default="can_mh")
    p.add_argument("--budget", type=int)
    a = p.parse_args()
    doc = build() if a.build else load()
    out = {"recommend": recommend(a.dataset, doc)}
    if a.budget:
        out["lookup"] = lookup(a.dataset, a.budget, doc)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
