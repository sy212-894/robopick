"""analyze_data: robomimic hdf5 데이터셋을 읽어 시범별 특징과 작업 조건 분포를 계산한다.

- 작업 조건: 물체(Can은 캔, Square는 너트) 초기 위치 (x, y)를 분위수 기준 격자로 나눈다 (기본 3x3).
  수직축 회전(yaw)은 두 데이터 모두 약 ±7도로 범위가 작아 계산만 하고 조건에는 쓰지 않는다
  (Can은 원통이라 원래 영향이 적고, Square는 2026-10-12 데이터 확인에서 ±7도로 측정).
- 품질 후보 신호: 경로 길이, 움직임 거칠기, 정지 비율, 그리퍼 개폐 횟수.
- 숙련도 라벨(worse/okay/better)은 선별에 쓰지 않고, 품질 신호가 맞는지 검증하는 데만 쓴다.
- 진단(2026-10-17, 선별 전에 사람이 보는 정보. 선별 방법은 바꾸지 않는다):
  편중 = 물체 초기 위치를 같은 넓이 3x3 칸으로 나눠 칸별 시범 수를 세고, 평균의 절반 미만인 칸을 부족으로 표시
  (조건 격자는 분위수라 칸마다 개수가 비슷하게 나뉘어 편중이 보이지 않는다. 그래서 진단은 같은 넓이로 본다).
  수집 계획 = 부족한 칸마다 평균 수준까지 더 모을 개수. 이 수집이 성공률을 높이는지는 실험하지 않았다.
  중복 = 팔 끝 궤적을 20점으로 줄여 두 시범의 평균 거리가 2cm 미만이면 거의 같은 시범으로 표시

사용: python -m curation_tools.analyze --dataset C:/curation-data/raw/can_mh_low_dim.hdf5
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

DEFAULT_OUT_ROOT = Path("C:/curation-data/runs")
QUALITY_LEVELS = ("worse", "okay", "better")
QUALITY_SIGNALS = ("path_length", "action_roughness", "idle_ratio", "gripper_switches")
OBJECT_LABEL = {"PickPlaceCan": "캔", "NutAssemblySquare": "너트", "Lift": "큐브"}  # 환경 이름 → 그림·설명에 쓸 물체 이름
DUP_THRESHOLD_M = 0.02  # 궤적 20점 평균 거리 2cm 미만 = 거의 같은 시범 (Can·Square 학습 후보에는 0쌍, 가장 가까운 쌍 약 3cm)
PATH_POINTS = 20
IDLE_THRESHOLD_M = 0.001  # 한 프레임(1/20초) 동안 팔 끝 이동이 1mm 미만이면 정지로 본다 (= 2cm/s 미만)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _yaw_from_xyzw(q: np.ndarray) -> float:
    """robosuite 관측의 쿼터니언(x, y, z, w)에서 수직축 회전각(라디안)을 구한다."""
    x, y, z, w = q
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def _labels(f: h5py.File) -> dict[str, dict]:
    """필터 키에서 시범별 숙련도·운영자·분할 정보를 읽는다. 숙련도 라벨이 없는 데이터(PH, 사용자 파일)도 읽는다."""
    mask = f["mask"]
    names = lambda key: {n.decode() if isinstance(n, bytes) else str(n) for n in mask[key][()]} if key in mask else set()
    info: dict[str, dict] = {}
    for level in QUALITY_LEVELS:
        for op in (1, 2):
            for demo in names(f"{level}_operator_{op}"):
                info.setdefault(demo, {})["quality"] = level
                info[demo]["operator"] = f"{level}_operator_{op}"
    train, valid = names("train"), names("valid")
    for demo in train | valid:
        info.setdefault(demo, {})
    for demo, d in info.items():
        d["split"] = "train" if demo in train else ("valid" if demo in valid else None)
    return info


def demo_features(demo: h5py.Group) -> dict:
    """시범 하나의 특징을 계산한다."""
    obs = demo["obs"]
    obj0 = obs["object"][0]
    eef = obs["robot0_eef_pos"][()]
    actions = demo["actions"][()]
    step = np.linalg.norm(np.diff(eef, axis=0), axis=1)
    arm_actions = actions[:, :6]
    grip = np.sign(actions[:, 6])
    grip = grip[grip != 0]
    return {
        "length": int(demo.attrs["num_samples"]),
        "init_x": float(obj0[0]),
        "init_y": float(obj0[1]),
        "init_yaw": _yaw_from_xyzw(obj0[3:7]),
        "path_length": float(step.sum()),
        "action_roughness": float(np.linalg.norm(np.diff(arm_actions, axis=0), axis=1).mean()),
        "idle_ratio": float((step < IDLE_THRESHOLD_M).mean()),
        "gripper_switches": int((np.diff(grip) != 0).sum()),
    }


def dataset_name(path: Path) -> str:
    """파일 이름에서 데이터셋 이름을 정한다 (can_mh_low_dim.hdf5 → can_mh)."""
    return Path(path).stem.replace("_low_dim", "")


def assign_conditions(demos: list[dict], grid: int, obj: str = "캔") -> dict:
    """물체 초기 위치 (x, y)를 분위수 경계로 grid x grid 칸에 나눈다."""
    xs = np.array([d["init_x"] for d in demos])
    ys = np.array([d["init_y"] for d in demos])
    qs = np.linspace(0, 1, grid + 1)
    x_edges, y_edges = np.quantile(xs, qs), np.quantile(ys, qs)
    # 안쪽 경계만 써서 칸 번호를 정한다 (양 끝 값도 마지막 칸에 들어가도록)
    xi = np.searchsorted(x_edges[1:-1], xs, side="right")
    yi = np.searchsorted(y_edges[1:-1], ys, side="right")
    for d, i, j in zip(demos, xi, yi):
        d["condition"] = f"x{i}y{j}"
    return {"grid": grid, "x_edges": x_edges.round(4).tolist(), "y_edges": y_edges.round(4).tolist(),
            "basis": f"{obj} 초기 위치 (x, y) 분위수 격자. yaw는 범위가 약 ±7도로 작아 제외"}


def condition_stats(demos: list[dict], grid: int) -> list[dict]:
    rows = []
    for i in range(grid):
        for j in range(grid):
            cid = f"x{i}y{j}"
            members = [d for d in demos if d["condition"] == cid]
            rows.append({
                "condition": cid,
                "count": len(members),
                "by_quality": {q: sum(d.get("quality") == q for d in members) for q in QUALITY_LEVELS},
                "mean_length": round(float(np.mean([d["length"] for d in members])), 1) if members else None,
                "total_frames": int(sum(d["length"] for d in members)),
            })
    return rows


def _rank(a: np.ndarray) -> np.ndarray:
    order = a.argsort(kind="mergesort")
    ranks = np.empty(len(a))
    ranks[order] = np.arange(len(a))
    for v in np.unique(a):  # 동점은 평균 순위
        idx = a == v
        ranks[idx] = ranks[idx].mean()
    return ranks


def spearman(x, y) -> float:
    rx, ry = _rank(np.asarray(x, float)), _rank(np.asarray(y, float))
    return float(np.corrcoef(rx, ry)[0, 1])


def signal_vs_quality(demos: list[dict]) -> dict:
    """품질 후보 신호를 숙련도별로 비교한다 (검증용, 선별에는 라벨을 쓰지 않는다)."""
    order = {"worse": 0, "okay": 1, "better": 2}
    labeled = [d for d in demos if d.get("quality") in order]
    if not labeled:
        return {}  # 숙련도 라벨이 없는 데이터는 신호 검증을 하지 않는다
    level = [order[d["quality"]] for d in labeled]
    out = {}
    for s in ("length",) + QUALITY_SIGNALS:
        vals = [d[s] for d in labeled]
        out[s] = {
            "mean_by_quality": {q: round(float(np.mean([d[s] for d in labeled if d["quality"] == q])), 4) for q in QUALITY_LEVELS},
            "spearman_with_skill": round(spearman(vals, level), 3),
        }
    return out


def _path(demo: h5py.Group) -> np.ndarray:
    e = demo["obs"]["robot0_eef_pos"][()]
    return e[np.linspace(0, len(e) - 1, PATH_POINTS).round().astype(int)]


def diagnose(demos: list[dict], paths: dict[str, np.ndarray], grid: int = 3) -> dict:
    """선별 후보(학습 분할, 없으면 전체)의 편중·중복·수집 계획."""
    pool = [d for d in demos if d.get("split") == "train"] or demos
    xs, ys = np.array([d["init_x"] for d in pool]), np.array([d["init_y"] for d in pool])
    xe, ye = np.linspace(xs.min(), xs.max(), grid + 1), np.linspace(ys.min(), ys.max(), grid + 1)
    xi = np.clip(np.searchsorted(xe[1:-1], xs, side="right"), 0, grid - 1)
    yi = np.clip(np.searchsorted(ye[1:-1], ys, side="right"), 0, grid - 1)
    counts = np.zeros((grid, grid), int)
    for a, b in zip(xi, yi):
        counts[a, b] += 1
    mean = counts.mean()
    cells = [{"cell": f"x{i}y{j}", "x": [round(float(xe[i]), 3), round(float(xe[i + 1]), 3)],
              "y": [round(float(ye[j]), 3), round(float(ye[j + 1]), 3)], "count": int(counts[i, j])}
             for i in range(grid) for j in range(grid)]
    low = [{**c, "need": int(np.ceil(mean - c["count"]))} for c in cells if c["count"] < 0.5 * mean]
    ids = [d["id"] for d in pool if d["id"] in paths]
    P = np.stack([paths[i] for i in ids])
    D = np.sqrt(((P[:, None] - P[None]) ** 2).sum(-1)).mean(-1)
    iu = np.triu_indices(len(ids), 1)
    order = np.argsort(D[iu])
    pairs = [{"a": ids[iu[0][k]], "b": ids[iu[1][k]], "distance_m": round(float(D[iu][k]), 4)}
             for k in order[:10] if D[iu][k] < DUP_THRESHOLD_M]
    return {
        "pool": len(pool),
        "coverage": {"grid": grid, "basis": "물체 초기 위치를 같은 넓이 칸으로 나눔 (선별 조건의 분위수 칸과 다름)",
                     "mean": round(float(mean), 1), "cells": cells, "low_cells": low,
                     "rule": "평균의 절반 미만 = 부족, 수집 계획 = 평균까지 더 모을 개수 (효과는 실험하지 않음)"},
        "collection_plan": [{"cell": c["cell"], "x": c["x"], "y": c["y"], "have": c["count"], "collect": c["need"]} for c in low],
        "duplicates": {"threshold_m": DUP_THRESHOLD_M, "n_pairs": int((D[iu] < DUP_THRESHOLD_M).sum()), "pairs": pairs,
                       "closest_m": round(float(D[iu].min()), 4) if len(ids) > 1 else None,
                       "rule": f"팔 끝 궤적 {PATH_POINTS}점 평균 거리 {DUP_THRESHOLD_M * 100:.0f}cm 미만 = 거의 같은 시범"},
    }


def analyze(dataset: Path, grid: int = 3) -> dict:
    with h5py.File(dataset, "r") as f:
        names = sorted(f["data"].keys(), key=lambda k: int(k.split("_")[1]))
        labels = _labels(f) if "mask" in f else {}
        demos, paths = [], {}
        for name in names:
            d = {"id": name, **demo_features(f["data"][name]), **labels.get(name, {})}
            demos.append(d)
            paths[name] = _path(f["data"][name])
        split_note = None
        if not any(d.get("split") for d in demos):
            # 학습/평가 분할(train 필터 키)이 없는 사용자 파일은 전체를 선별 후보로 쓴다
            for d in demos:
                d["split"] = "train"
            split_note = "train 필터 키가 없어 시범 전체를 선별 후보로 썼다"
        env_name = json.loads(f["data"].attrs["env_args"]).get("env_name")
    obj = OBJECT_LABEL.get(env_name, "물체")
    cond_def = assign_conditions(demos, grid, obj)
    return {
        "dataset": {"name": dataset_name(dataset), "path": str(dataset), "sha256": _sha256(dataset), "env_name": env_name, "object": obj,
                    "n_demos": len(demos), "total_frames": int(sum(d["length"] for d in demos)),
                    "n_candidates": sum(d.get("split") == "train" for d in demos), "split_note": split_note},
        "condition_definition": cond_def,
        "conditions": condition_stats(demos, grid),
        "signal_vs_quality": signal_vs_quality(demos),
        "diagnosis": diagnose(demos, paths),
        "demos": demos,
    }


def summarize(result: dict) -> dict:
    """LLM에 넘길 요약본: 시범별 목록과 숙련도 라벨을 빼고 조건별 통계만 남긴다."""
    lengths = [d["length"] for d in result["demos"]]
    return {
        "run_id": result["run_id"],
        "dataset": {k: result["dataset"][k] for k in ("name", "env_name", "n_demos", "total_frames", "n_candidates", "split_note") if k in result["dataset"]},
        "length": {"min": int(min(lengths)), "mean": round(float(np.mean(lengths)), 1), "max": int(max(lengths))},
        "condition_definition": result["condition_definition"],
        "conditions": [{k: c[k] for k in ("condition", "count", "mean_length", "total_frames")} for c in result["conditions"]],
        "quality_signals": list(QUALITY_SIGNALS),
        "diagnosis": _diag_summary(result.get("diagnosis")),
        "rule_check": result.get("rule_check"),
    }


def _diag_summary(diag: dict | None) -> dict | None:
    """LLM에는 중복 쌍의 시범 ID를 빼고 개수와 거리만 넘긴다 (전체 목록은 analysis.json에 있다)."""
    if not diag:
        return diag
    dup = {k: v for k, v in diag["duplicates"].items() if k != "pairs"}
    dup["pair_distances_m"] = [p["distance_m"] for p in diag["duplicates"]["pairs"]]
    return {**diag, "duplicates": dup}


def plot_positions(result: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    markers = {"worse": "x", "okay": "^", "better": "o"}
    cmap = plt.get_cmap("tab10")
    conds = [c["condition"] for c in result["conditions"]]
    for q, m in markers.items():
        pts = [d for d in result["demos"] if d.get("quality") == q]
        ax.scatter([d["init_x"] for d in pts], [d["init_y"] for d in pts], marker=m, s=28,
                   c=[cmap(conds.index(d["condition"])) for d in pts], label=q, alpha=0.85)
    cd = result["condition_definition"]
    for e in cd["x_edges"][1:-1]:
        ax.axvline(e, color="gray", ls="--", lw=0.8)
    for e in cd["y_edges"][1:-1]:
        ax.axhline(e, color="gray", ls="--", lw=0.8)
    obj = result["dataset"].get("object", "캔")
    ax.set_xlabel(f"{obj} 초기 위치 x (m)")
    ax.set_ylabel(f"{obj} 초기 위치 y (m)")
    ax.set_title(f"{obj} 초기 위치와 작업 조건 ({cd['grid']}x{cd['grid']}) · 시범 {result['dataset']['n_demos']}개")
    # 색은 조건을 뜻하므로, 숙련도 범례는 모양만 보이도록 회색 마커로 따로 그린다
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker=m, ls="", color="dimgray", label=q) for q, m in markers.items()]
    ax.legend(handles=handles, title="숙련도 (모양) · 색 = 조건", loc="best")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def run(dataset: Path, out_root: Path = DEFAULT_OUT_ROOT, grid: int = 3, run_id: str | None = None) -> Path:
    run_id = run_id or "R-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_root / run_id
    out.mkdir(parents=True, exist_ok=True)
    result = {"run_id": run_id, "created_at": dt.datetime.now().isoformat(timespec="seconds"), **analyze(dataset, grid)}
    from curation_tools.rule_check import check  # select_demos가 이 모듈을 불러 순환을 피한다
    result["rule_check"] = check(result["demos"])
    (out / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "analysis_summary.json").write_text(json.dumps(summarize(result), ensure_ascii=False, indent=1), encoding="utf-8")
    plot_positions(result, out / "initial_positions.png")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--grid", type=int, default=3)
    p.add_argument("--run-id")
    a = p.parse_args()
    out = run(a.dataset, a.out_root, a.grid, a.run_id)
    print(f"[analyze_data] 저장: {out}")


if __name__ == "__main__":
    main()
