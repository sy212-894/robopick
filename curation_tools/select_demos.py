"""select_demos: analyze_data 결과를 읽어 예산만큼 시범을 고르고, 비교용 무작위 기준선을 함께 만든다.

- 후보: train 분할만 쓴다. valid는 학습 중 검증용이라 선별에 쓰지 않는다.
- 품질 점수: 길이·정지 비율·경로 길이·그리퍼 개폐 횟수의 순위 백분위 평균 (작을수록 좋음, 가중치 동일).
  숙련도 라벨은 선별에 쓰지 않고, 선택 결과를 사후 확인하는 데만 쓴다.
- 배분: 예산을 조건 칸 크기 비율로 나누고(최대 나머지 방식), 칸 안에서 품질 점수 순으로 고른다.
- 기준선: 같은 개수 무작위(random_N), 총 프레임을 맞춘 무작위(random_frames),
  조건별 균등 선택(stratified_random_N: 칸별 개수는 같고 칸 안은 무작위).
- 원본 hdf5는 건드리지 않고, 복사본 하나에 필터 키(mask/<이름>)를 넣는다.

사용: python -m curation_tools.select_demos --analysis C:/curation-data/runs/R-20261011-analyze01/analysis.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import time
from pathlib import Path

import h5py
import numpy as np

from curation_tools.analyze import DEFAULT_OUT_ROOT, QUALITY_LEVELS, _rank

SCORE_SIGNALS = ("length", "idle_ratio", "path_length", "gripper_switches")  # 1단계 검증표 기준, 움직임 거칠기는 제외
DEFAULT_BUDGET = 150
FRAME_TOLERANCE = 0.02  # random_frames의 총 프레임을 curated와 ±2% 안으로 맞춘다


def candidates(demos: list[dict]) -> list[dict]:
    return [d for d in demos if d.get("split") == "train"]


def quality_scores(pool: list[dict], signals: tuple[str, ...] = SCORE_SIGNALS) -> dict[str, float]:
    """신호마다 후보 안에서의 순위 백분위(0=가장 작음)를 구해 평균한다. 낮을수록 좋은 시범."""
    n = len(pool)
    pct = [_rank(np.array([d[s] for d in pool], float)) / (n - 1) for s in signals]
    mean = np.mean(pct, axis=0)
    return {d["id"]: round(float(v), 4) for d, v in zip(pool, mean)}


def allocate(pool: list[dict], budget: int) -> dict[str, int]:
    """예산을 칸 크기 비율로 나눈다. 내림한 뒤 남는 개수는 소수점 아래가 큰 칸부터 1개씩 준다."""
    counts: dict[str, int] = {}
    for d in pool:
        counts[d["condition"]] = counts.get(d["condition"], 0) + 1
    total = sum(counts.values())
    quota = {c: budget * k / total for c, k in counts.items()}
    planned = {c: int(q) for c, q in quota.items()}
    rest = budget - sum(planned.values())
    for c in sorted(quota, key=lambda c: (-(quota[c] - planned[c]), c))[:rest]:
        planned[c] += 1
    return dict(sorted(planned.items()))


def select_curated(pool: list[dict], scores: dict[str, float], planned: dict[str, int]) -> tuple[list[str], list[dict]]:
    selected, allocation = [], []
    for cond, want in planned.items():
        members = sorted((d for d in pool if d["condition"] == cond), key=lambda d: (scores[d["id"]], d["id"]))
        picked = [d["id"] for d in members[:want]]
        selected += picked
        allocation.append({"condition": cond, "available": len(members), "planned": want,
                           "selected": len(picked), "shortage": want - len(picked)})
    return selected, allocation


def random_count(pool: list[dict], n: int, rng: np.random.Generator) -> list[str]:
    idx = rng.choice(len(pool), size=n, replace=False)
    return [pool[i]["id"] for i in sorted(idx)]


def random_frames(pool: list[dict], target: int, rng: np.random.Generator, tol: float = FRAME_TOLERANCE) -> list[str]:
    """무작위 순서로 시범을 더해 총 프레임이 target의 ±tol 안에 들어오게 한다. 넘치는 시범은 건너뛴다."""
    lo, hi = target * (1 - tol), target * (1 + tol)
    picked, frames = [], 0
    for i in rng.permutation(len(pool)):
        d = pool[i]
        if frames + d["length"] > hi:
            continue
        picked.append(d["id"])
        frames += d["length"]
        if frames >= lo:
            break
    return sorted(picked, key=lambda s: int(s.split("_")[1]))


def stratified_random(pool: list[dict], planned: dict[str, int], rng: np.random.Generator) -> list[str]:
    """조건별 균등 기준선: 칸마다 curated와 같은 개수를 고르되 칸 안에서는 무작위로 고른다.
    curated와 비교하면 "품질 점수의 효과"만, random과 비교하면 "칸별 배분의 효과"만 볼 수 있다."""
    picked = []
    for cond, want in planned.items():
        members = [d["id"] for d in pool if d["condition"] == cond]
        take = min(want, len(members))
        picked += [members[i] for i in sorted(rng.choice(len(members), size=take, replace=False))]
    return _sort_ids(picked)


def _sort_ids(ids: list[str]) -> list[str]:
    return sorted(ids, key=lambda s: int(s.split("_")[1]))


def check(name: str, ids: list[str], demos_by_id: dict[str, dict], budget_demos: int | None) -> list[dict]:
    """5주차 검수자 점검 항목 중 도구 단계에서 확인할 수 있는 것: 예산, 중복, 평가용 ID 포함."""
    issues = []
    if budget_demos is not None and len(ids) > budget_demos:
        issues.append({"check": "budget", "detail": f"{name}: {len(ids)}개 > 예산 {budget_demos}개"})
    if len(set(ids)) != len(ids):
        issues.append({"check": "duplicate", "detail": f"{name}: 중복 ID {len(ids) - len(set(ids))}개"})
    leaked = [i for i in ids if demos_by_id[i].get("split") != "train"]
    if leaked:
        issues.append({"check": "eval_leak", "detail": f"{name}: train이 아닌 ID {len(leaked)}개 포함"})
    return issues


def label_breakdown(ids: list[str], demos_by_id: dict[str, dict]) -> dict[str, int]:
    """사후 확인용: 고른 시범의 숙련도 구성 (선별에는 쓰지 않는다)."""
    return {q: sum(demos_by_id[i].get("quality") == q for i in ids) for q in QUALITY_LEVELS}


def position_shift(pool: list[dict], selected: set[str]) -> list[dict]:
    """칸 안에서 고른 시범이 한쪽으로 쏠렸는지: 고른 것과 안 고른 것의 평균 위치 차이(cm)를 칸 안 위치 퍼짐(cm)과 비교한다."""
    rows = []
    for cond in sorted({d["condition"] for d in pool}):
        members = [d for d in pool if d["condition"] == cond]
        xy = lambda ds: np.array([[d["init_x"], d["init_y"]] for d in ds])
        sel = xy([d for d in members if d["id"] in selected])
        rest = xy([d for d in members if d["id"] not in selected])
        if len(sel) == 0 or len(rest) == 0:
            continue
        shift = float(np.linalg.norm(sel.mean(0) - rest.mean(0))) * 100
        spread = float(np.linalg.norm(xy(members).std(0))) * 100
        rows.append({"condition": cond, "shift_cm": round(shift, 2), "spread_cm": round(spread, 2),
                     "shift_ratio": round(shift / spread, 2) if spread else None})
    return rows


def shift_reference(pool: list[dict], n: int, runs: int = 100) -> dict:
    """무작위로 n개를 runs번 뽑았을 때 칸별 쏠림 비율의 분포. curated 쏠림이 우연 수준인지 판단하는 기준."""
    vals = []
    for s in range(runs):
        ids = random_count(pool, n, np.random.default_rng(10_000 + s))
        vals += [r["shift_ratio"] for r in position_shift(pool, set(ids)) if r["shift_ratio"] is not None]
    return {"random_runs": runs, "mean": round(float(np.mean(vals)), 2), "p95": round(float(np.percentile(vals, 95)), 2)}


def select(analysis: dict, budget: int = DEFAULT_BUDGET, seed: int = 0, signals: tuple[str, ...] = SCORE_SIGNALS) -> dict:
    t0 = time.perf_counter()
    demos_by_id = {d["id"]: d for d in analysis["demos"]}
    pool = candidates(analysis["demos"])
    scores = quality_scores(pool, signals)
    planned = allocate(pool, budget)
    curated, allocation = select_curated(pool, scores, planned)
    curated = _sort_ids(curated)
    curated_frames = sum(demos_by_id[i]["length"] for i in curated)
    t_select = time.perf_counter() - t0

    rng = np.random.default_rng(seed)
    sets = {
        f"curated_{budget}": curated,
        f"random_{budget}": random_count(pool, budget, rng),
        "random_frames": random_frames(pool, curated_frames, rng),
    }
    # 앞의 두 기준선과 같은 rng를 이어서 쓴다 (기존 기준선 결과가 바뀌지 않게 맨 뒤에 추가)
    sets[f"stratified_random_{budget}"] = stratified_random(pool, planned, rng)
    frames_of = lambda ids: int(sum(demos_by_id[i]["length"] for i in ids))
    issues = []
    for name, ids in sets.items():
        issues += check(name, ids, demos_by_id, None if name == "random_frames" else budget)
    if sum(a["selected"] for a in allocation) != len(curated):
        issues.append({"check": "allocation", "detail": "칸별 선택 합이 전체 선택 수와 다름"})
    rf = frames_of(sets["random_frames"])
    if abs(rf - curated_frames) > curated_frames * FRAME_TOLERANCE:
        issues.append({"check": "frame_match", "detail": f"random_frames {rf} vs curated {curated_frames}"})
    shift = position_shift(pool, set(curated))
    ref = shift_reference(pool, len(curated))
    over = [r["condition"] for r in shift if r["shift_ratio"] is not None and r["shift_ratio"] > ref["p95"]]
    if over:  # 위치 정보는 라벨이 아니므로 선별 규칙 점검에 써도 된다
        issues.append({"check": "position_shift", "detail": f"칸 안 위치 쏠림이 무작위 95% 기준({ref['p95']})을 넘음: {over}"})

    return {
        "analysis_run_id": analysis["run_id"],
        "data_version": analysis["dataset"]["sha256"],
        "pool": {"split": "train", "n_demos": len(pool), "total_frames": frames_of([d["id"] for d in pool])},
        "budget": {"demos": budget, "frames": curated_frames},
        "allocation": allocation,
        "selected_ids": curated,
        "total_frames": curated_frames,
        "settings": {"method": "조건별 비례 배분 + 칸 안 품질 점수 순", "score_signals": list(signals),
                     "weights": "동일", "score": "신호별 순위 백분위 평균, 낮을수록 좋음",
                     "seed": seed, "frame_tolerance": FRAME_TOLERANCE},
        "sets": {name: {"n_demos": len(ids), "total_frames": frames_of(ids), "ids": ids} for name, ids in sets.items()},
        "checks": {"verdict": "pass" if not issues else "revise", "issues": issues},
        "position_shift": {"curated": shift, "random_reference": ref},
        "validation_only": {
            "note": "숙련도 라벨은 선별에 쓰지 않았고, 아래는 사후 확인용이다",
            "quality_breakdown": {name: label_breakdown(ids, demos_by_id) for name, ids in sets.items()},
        },
        "scores": scores,
        "timing_sec": {"select": round(t_select, 3)},
    }


def summarize(result: dict) -> dict:
    """LLM에 넘길 요약본: ID 목록, 점수, 숙련도 라벨을 뺀다."""
    return {
        "run_id": result["run_id"],
        "analysis_run_id": result["analysis_run_id"],
        "pool": result["pool"],
        "budget": result["budget"],
        "allocation": result["allocation"],
        "settings": result["settings"],
        "sets": {k: {"n_demos": v["n_demos"], "total_frames": v["total_frames"]} for k, v in result["sets"].items()},
        "checks": result["checks"],
        "hdf5_filter_keys": result["hdf5"]["filter_keys"],
    }


def write_filtered_copy(src: Path, dst: Path, sets: dict[str, list[str]]) -> None:
    """원본을 복사하고 복사본에만 필터 키를 넣는다. robomimic은 train.hdf5_filter_key로 이 키를 쓴다."""
    shutil.copy2(src, dst)
    with h5py.File(dst, "a") as f:
        for name, ids in sets.items():
            key = f"mask/{name}"
            if key in f:
                del f[key]
            f.create_dataset(key, data=np.array(ids, dtype="S"))


def curated_filename(analysis: dict) -> str:
    """필터 키를 넣은 복사본 파일 이름 (예: can_mh_curated.hdf5, square_mh_curated.hdf5)."""
    return f"{analysis['dataset'].get('name', 'can_mh')}_curated.hdf5"


def run(analysis_path: Path, out_root: Path = DEFAULT_OUT_ROOT, budget: int = DEFAULT_BUDGET,
        seed: int = 0, run_id: str | None = None, write_hdf5: bool = True,
        signals: tuple[str, ...] = SCORE_SIGNALS) -> Path:
    analysis = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
    run_id = run_id or "R-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(out_root) / run_id
    out.mkdir(parents=True, exist_ok=True)
    result = {"run_id": run_id, "created_at": dt.datetime.now().isoformat(timespec="seconds"),
              **select(analysis, budget, seed, signals)}
    hdf5_path = out / curated_filename(analysis)
    t0 = time.perf_counter()
    if write_hdf5:
        write_filtered_copy(Path(analysis["dataset"]["path"]), hdf5_path,
                            {k: v["ids"] for k, v in result["sets"].items()})
    result["timing_sec"]["write_hdf5"] = round(time.perf_counter() - t0, 3)
    result["hdf5"] = {"path": str(hdf5_path) if write_hdf5 else None, "filter_keys": list(result["sets"])}
    (out / "selection.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "selection_summary.json").write_text(json.dumps(summarize(result), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--analysis", type=Path, required=True)
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--run-id")
    p.add_argument("--no-hdf5", action="store_true", help="필터 키 복사본을 만들지 않는다")
    # 한계 점검용 (docs/10_robustness.md): 기본은 1단계에서 정한 신호 4개. 예) --signals length  또는 5개 모두
    p.add_argument("--signals", nargs="+", default=list(SCORE_SIGNALS), help="품질 점수에 쓸 신호 (같은 가중치)")
    a = p.parse_args()
    out = run(a.analysis, a.out_root, a.budget, a.seed, a.run_id, not a.no_hdf5, tuple(a.signals))
    print(f"[select_demos] 저장: {out}")


if __name__ == "__main__":
    main()
