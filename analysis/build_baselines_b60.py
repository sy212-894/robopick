"""예산 60개 기준선 비교 실험의 선별을 만든다 (docs/10_robustness.md, 한계 2·9).

예산을 줄이면 기준선마다 고르는 시범이 확실히 달라져서 학습 결과로 비교할 수 있다. 1차·2차 묶음을 모두
한 선별 파일(한 학습 계획)에 넣어 결과를 보기 전에 확정한다. 노트북마다 학습할 묶음만 고른다.

묶음 (모두 예산 60, 같은 분석 R-20261011-analyze01, train 분할 270개 후보)
- curated_60, random_60, stratified_random_60, random_frames: 기존 선별 도구 (신호 4개, 선별 난수 0)
- length_60, gripper_60, nolength3_60, idle_60, path_60: 신호만 바꾼 선별 도구의 선별 묶음 (칸별 배분 같음)
- diversity_60: 캔 초기 위치(x, y, 후보 범위로 0~1 정규화)가 최대한 퍼지게 하나씩 고르기 (가장 먼 점 먼저).
  첫 시범은 후보 중심에 가장 가까운 것. 칸 배분 없음 (다양성 접근 그 자체)
- longest_60: 칸별 배분은 같고 칸 안에서 가장 긴 시범부터 (품질 방향 점검용)

사용: python analysis/build_baselines_b60.py  → C:/curation-data/runs/R-20261013-select-b60/selection.json
그다음 train_evaluate.prepare로 학습 계획을 만든다.
"""
import datetime as dt
import json
import math
from pathlib import Path

from curation_tools import select_demos as S

RUNS = Path("C:/curation-data/runs")
ANALYSIS = RUNS / "R-20261011-analyze01" / "analysis.json"
RUN_ID = "R-20261013-select-b60"
BUDGET = 60
VARIANTS = {  # 묶음 이름: 품질 점수에 쓸 신호
    "length_60": ("length",),
    "gripper_60": ("gripper_switches",),
    "nolength3_60": ("idle_ratio", "path_length", "gripper_switches"),
    "idle_60": ("idle_ratio",),
    "path_60": ("path_length",),
}


def diversity(pool: list[dict], n: int) -> list[str]:
    xs, ys = [d["init_x"] for d in pool], [d["init_y"] for d in pool]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pt = {d["id"]: ((d["init_x"] - x0) / (x1 - x0), (d["init_y"] - y0) / (y1 - y0)) for d in pool}
    cx = sum(p[0] for p in pt.values()) / len(pt)
    cy = sum(p[1] for p in pt.values()) / len(pt)
    order = sorted(pt, key=lambda i: int(i.split("_")[1]))   # 같은 거리면 번호가 작은 것
    first = min(order, key=lambda i: math.dist(pt[i], (cx, cy)))
    chosen, near = [first], {i: math.dist(pt[i], pt[first]) for i in order}
    while len(chosen) < n:
        nxt = max((i for i in order if i not in chosen), key=lambda i: near[i])
        chosen.append(nxt)
        for i in order:
            near[i] = min(near[i], math.dist(pt[i], pt[nxt]))
    return chosen


def longest(pool: list[dict], planned: dict[str, int]) -> list[str]:
    out = []
    for cell, k in planned.items():
        ds = sorted((d for d in pool if d["condition"] == cell), key=lambda d: (-d["length"], int(d["id"].split("_")[1])))
        out += [d["id"] for d in ds[:k]]
    return out


def main() -> None:
    an = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    pool = S.candidates(an["demos"])
    by_id = {d["id"]: d for d in pool}
    base = S.select(an, BUDGET, 0)
    sets = {k: v["ids"] for k, v in base["sets"].items()}
    for name, sig in VARIANTS.items():
        sets[name] = S.select(an, BUDGET, 0, sig)["selected_ids"]
    sets["diversity_60"] = diversity(pool, BUDGET)
    sets["longest_60"] = longest(pool, {a["condition"]: a["planned"] for a in base["allocation"]})
    sets = {k: S._sort_ids(v) for k, v in sets.items()}
    cur = set(sets[f"curated_{BUDGET}"])
    frames = lambda ids: sum(by_id[i]["length"] for i in ids)  # noqa: E731
    result = {**base, "run_id": RUN_ID, "created_at": dt.datetime.now().isoformat(timespec="seconds"),
              "settings": {**base["settings"], "baselines": {k: list(v) for k, v in VARIANTS.items()},
                           "diversity_60": "캔 초기 위치 최대 분산 (가장 먼 점 먼저, 칸 배분 없음)",
                           "longest_60": "칸별 배분 같음, 칸 안에서 가장 긴 시범부터",
                           "note": "docs/10_robustness.md 예산 60 기준선 비교. 결과 보기 전에 확정"},
              "sets": {k: {"n_demos": len(v), "total_frames": frames(v), "ids": v,
                           "overlap_with_curated": len(set(v) & cur)} for k, v in sets.items()},
              "validation_only": {**base["validation_only"],
                                  "quality_breakdown": {k: S.label_breakdown(v, by_id) for k, v in sets.items()}}}
    out = RUNS / RUN_ID
    out.mkdir(parents=True, exist_ok=True)
    (out / "selection.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in result["sets"].items():
        print(f"{k:22s} {v['n_demos']:3d} demos {v['total_frames']:6d} frames  overlap {v['overlap_with_curated']:2d}/60  "
              f"{result['validation_only']['quality_breakdown'][k]}")
    print("저장:", out / "selection.json")


if __name__ == "__main__":
    main()
