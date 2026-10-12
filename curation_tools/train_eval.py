"""train_evaluate: 학습 계획을 만들고(prepare), 코랩 학습 결과를 모아 비교한다(collect).

학습 자체는 코랩(colab/01_train_eval.ipynb)에서 돈다. 몇 시간이 걸려서 대화와 분리했다 (7주차 설계 2-6).
- prepare: 묶음별 시범 번호와 학습 설정을 plan.json으로 저장. 같은 묶음·설정이면 같은 지문(fingerprint)
- collect: results.json을 읽어 비교표와 1주차 성공 기준 판정을 만든다. 판정은 코드가 한다 (LLM 아님)
  같은 지문의 결과가 이미 있으면 다시 학습하지 않고 재사용한다 (재사용했다는 사실과 실행 시각을 함께 돌려준다)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path

RESULTS_STORE = Path("C:/curation-data/results_store")  # 지문별 학습 결과 (재사용용)
HF_REPO = "robomimic/robomimic_datasets"
DATASETS = {  # 데이터셋 이름 → Hugging Face 경로 (노트북이 이 경로로 내려받는다)
    "can_mh": {"hf_repo": HF_REPO, "hf_path": "v1.5/can/mh/low_dim_v15.hdf5"},
    "square_mh": {"hf_repo": HF_REPO, "hf_path": "v1.5/square/mh/low_dim_v15.hdf5"},
}
# 파일럿(5-4, 2026-10-11) 결과로 확정: BC는 전체 데이터로도 20% 안팎(바닥), BC-RNN은 400 epoch에서 전체 10/10, 무작위 150 8/10.
# 200 epoch 시점 차이가 가장 커서(7/10 vs 3/10) 학습 속도 비교용 중간 평가를 둔다. LLM이 바꾸지 못하도록 도구 인자로 받지 않는다
TRAIN_CONFIG = {"algo": "bc_rnn", "num_epochs": 400, "steps_per_epoch": 100, "batch_size": 100,
                "seed": 1, "rollout_n": 50, "rollout_horizon": 400, "early_eval_epoch": 200, "early_eval_n": 30}
# Square는 Can과 같은 설정으로 시작한다 (파일럿에서 성공률이 바닥이면 epoch를 늘리는 식으로 조정, 6-4)
TRAIN_CONFIGS = {"can_mh": TRAIN_CONFIG, "square_mh": dict(TRAIN_CONFIG)}
MINUTES_PER_SET = 22  # 본 실험 측정(2026-10-12, T4): BC-RNN 학습 약 10분 + 평가(30회 + 50회) 약 12분
TARGET_GAIN = 0.05     # 1주차: 같은 개수 무작위보다 +5%p
MAX_DROP = 0.05        # 1주차: 전체 데이터 대비 하락 5%p 이내
MIN_TRAIN_SUCCESS = 0.2  # 전체 데이터 기준선이 이보다 낮으면 판정 불가 (학습 자체가 실패)


def _order(names: list[str]) -> list[str]:
    """중요한 묶음부터 학습하도록 순서를 정한다 (세션이 끊겨도 핵심 비교가 먼저 남게)."""
    def key(n: str) -> int:
        if n.startswith("curated"):
            return 0
        if n == "random_frames":
            return 3
        if n.startswith("random_"):
            return 1
        if n.startswith("stratified"):
            return 2
        return 4 if n == "train" else 5
    return sorted(names, key=key)


def compact_plan(plan: dict) -> str:
    """코랩 셀에 붙여 넣을 한 줄 문자열 (zlib + base64). 시범 이름은 번호만 남긴다."""
    import base64
    import zlib
    body = {"fp": plan["fingerprint"], "run_id": plan["run_id"], "dataset": plan["dataset"]["name"],
            "hf_path": plan["dataset"]["hf_path"], "config": plan["config"], "order": plan["order"],
            "sets": {k: [int(i.split("_")[1]) for i in v] for k, v in plan["sets"].items()}}
    return base64.b64encode(zlib.compress(json.dumps(body, separators=(",", ":")).encode(), 9)).decode()


def fingerprint(sets: dict[str, list[str]], config: dict, data_sha: str) -> str:
    body = json.dumps({"sets": {k: sorted(v) for k, v in sorted(sets.items())}, "config": config, "data": data_sha},
                      sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def prepare(run_dir: Path, runs_root: Path, config: dict | None = None) -> dict:
    sel = json.loads((run_dir / "selection.json").read_text(encoding="utf-8"))
    analysis = json.loads((runs_root / sel["analysis_run_id"] / "analysis.json").read_text(encoding="utf-8"))
    name = analysis["dataset"].get("name", "can_mh")
    if name not in DATASETS:
        raise ValueError(f"학습 계획을 만들 수 없는 데이터셋: {name}")
    config = dict(config or TRAIN_CONFIGS[name])
    sets = {name: s["ids"] for name, s in sel["sets"].items()}
    sets["train"] = sorted((d["id"] for d in analysis["demos"] if d.get("split") == "train"),
                           key=lambda s: int(s.split("_")[1]))
    fp = fingerprint(sets, config, analysis["dataset"]["sha256"])
    plan = {"run_id": sel["run_id"], "analysis_run_id": sel["analysis_run_id"], "fingerprint": fp,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "dataset": {"name": name, **DATASETS[name], "sha256": analysis["dataset"]["sha256"]},
            "config": config, "order": _order(list(sets)), "sets": sets}
    out = run_dir / "plan"
    out.mkdir(exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (out / "plan_b64.txt").write_text(compact_plan(plan), encoding="ascii")
    return {"run_id": sel["run_id"], "dataset": name, "fingerprint": fp, "status": "prepared",
            "n_sets": len(sets), "order": plan["order"],
            "sets": {k: len(v) for k, v in sets.items()},
            "config": config, "est_minutes": len(sets) * MINUTES_PER_SET,
            "notebook": "colab/01_train_eval.ipynb",
            "already_trained": (RESULTS_STORE / f"{fp}.json").exists()}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """성공률 95% 신뢰구간 (윌슨 방법, 0%나 100% 근처에서도 안정적)."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


def diff(a: dict, b: dict, z: float = 1.96) -> dict:
    """a - b 성공률 차이와 95% 신뢰구간 (정규 근사), 3단계 판정."""
    pa, pb = a["success"] / a["rollouts"], b["success"] / b["rollouts"]
    se = math.sqrt(pa * (1 - pa) / a["rollouts"] + pb * (1 - pb) / b["rollouts"])
    d = pa - pb
    lo, hi = d - z * se, d + z * se
    verdict = "차이 있음 (높음)" if lo > 0 else ("더 나쁨" if hi < 0 else "구분 불가")
    return {"diff": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)], "verdict": verdict}


def _early(r: dict, config: dict) -> dict | None:
    """중간 평가(학습 속도) 결과. 없으면 None."""
    ep = config.get("early_eval_epoch")
    return (r.get("by_epoch") or {}).get(str(ep)) if ep else None


def runs_by_set(results: dict, seeds: dict | None = None) -> dict[str, list[dict]]:
    """묶음별 학습 결과 목록. 시드 1(results.json)과 추가 시드(results_seeds.json의 runs)를 합친다."""
    base_seed = results.get("config", {}).get("seed", 1)
    out: dict[str, list[dict]] = {k: [{**v, "seed": base_seed}] for k, v in results["sets"].items()}
    for r in (seeds or {}).get("runs", {}).values():
        if all(x["seed"] != r["seed"] for x in out.get(r["set"], [])):
            out.setdefault(r["set"], []).append(r)
    return {k: sorted(v, key=lambda x: x["seed"]) for k, v in out.items()}


def _pool(runs: list[dict], early_epoch: int | None = None) -> dict | None:
    """여러 시드의 롤아웃을 합친다. early_epoch를 주면 그 epoch의 중간 평가를 합친다."""
    rows = [(r.get("by_epoch") or {}).get(str(early_epoch)) for r in runs] if early_epoch else runs
    if not rows or any(x is None for x in rows):
        return None
    return {"success": sum(x["success"] for x in rows), "rollouts": sum(x["rollouts"] for x in rows),
            "per_seed": {r["seed"]: x["success"] / x["rollouts"] for r, x in zip(runs, rows)}}


def diff_runs(a: dict, b: dict) -> dict:
    """a - b 비교. 롤아웃을 합친 차이의 95% 신뢰구간에 더해, 시드가 여러 개면 시드마다 차이를 본다.
    시드 여러 개일 때 "차이 있음"은 신뢰구간이 0을 넘고 같은 시드끼리 비교해 모든 시드에서 같은 방향일 때만이다
    (롤아웃 신뢰구간에는 시드 사이 흔들림이 빠져 있어서, 한 시드에서만 크게 이긴 경우를 걸러낸다)."""
    d = diff(a, b)
    common = sorted(set(a["per_seed"]) & set(b["per_seed"]))
    d["n_seeds"] = len(common)
    if len(common) >= 2:
        per = [round(a["per_seed"][s] - b["per_seed"][s], 4) for s in common]
        d["per_seed_diff"] = dict(zip(common, per))
        if d["verdict"] == "차이 있음 (높음)" and not all(x > 0 for x in per):
            d["verdict"], d["note"] = "구분 불가", "신뢰구간은 0보다 크지만 시드마다 방향이 다름"
        if d["verdict"] == "더 나쁨" and not all(x < 0 for x in per):
            d["verdict"], d["note"] = "구분 불가", "신뢰구간은 0보다 작지만 시드마다 방향이 다름"
    return d


def compare(plan: dict, results: dict, seeds: dict | None = None) -> dict:
    runs = runs_by_set(results, seeds)
    ep = plan["config"].get("early_eval_epoch")
    pooled = {k: _pool(v) for k, v in runs.items()}
    early = {k: _pool(v, ep) for k, v in runs.items()} if ep else {}
    table = []
    for name in plan["order"]:
        row = {"set": name, "n_demos": len(plan["sets"][name])}
        if name in runs:
            p, rs = pooled[name], runs[name]
            rates = [r["success"] / r["rollouts"] for r in rs]
            row.update({"n_seeds": len(rs), "success": p["success"], "rollouts": p["rollouts"],
                        "success_rate": round(p["success"] / p["rollouts"], 4),
                        "ci95": wilson(p["success"], p["rollouts"]),
                        "per_seed": [{"seed": r["seed"], "success": r["success"], "rollouts": r["rollouts"]} for r in rs],
                        "train_min": round(sum(r.get("train_sec", 0) for r in rs) / len(rs) / 60, 1)})
            if len(rs) > 1:
                row["seed_range"] = [round(min(rates), 4), round(max(rates), 4)]
            if early.get(name):
                e = early[name]
                row["early"] = {"epoch": ep, "success": e["success"], "rollouts": e["rollouts"],
                                "success_rate": round(e["success"] / e["rollouts"], 4)}
        else:
            row["status"] = "결과 없음"
        table.append(row)
    cur = next((n for n in runs if n.startswith("curated")), None)
    rnd = next((n for n in runs if n.startswith("random_") and n != "random_frames"), None)
    strat = next((n for n in runs if n.startswith("stratified")), None)
    judge = {}
    train = pooled.get("train")
    if train and train["success"] / train["rollouts"] < MIN_TRAIN_SUCCESS:
        judge["validity"] = f"판정 불가: 전체 데이터 기준선 성공률이 {MIN_TRAIN_SUCCESS:.0%} 미만 (학습 설정 문제)"
    if cur and rnd:
        d = diff_runs(pooled[cur], pooled[rnd])
        judge["gain_vs_random"] = {**d, "target": TARGET_GAIN, "meets_target_point": d["diff"] >= TARGET_GAIN,
                                   "question": f"{cur}가 {rnd}보다 {TARGET_GAIN:.0%}p 이상 높은가"}
    if cur and train:
        d = diff_runs(train, pooled[cur])
        judge["drop_vs_full"] = {**d, "target": MAX_DROP, "meets_target_point": d["diff"] <= MAX_DROP,
                                 "confirmed": d["ci95"][1] <= MAX_DROP,
                                 "question": f"전체 대비 {cur}의 하락이 {MAX_DROP:.0%}p 이내인가"}
    if strat and rnd:
        judge["effect_allocation"] = {**diff_runs(pooled[strat], pooled[rnd]), "question": "칸별 배분의 효과 (조건별 균등 - 무작위)"}
    if cur and strat:
        judge["effect_quality"] = {**diff_runs(pooled[cur], pooled[strat]), "question": "품질 점수의 효과 (선별 - 조건별 균등)"}
    if cur and rnd and early.get(cur) and early.get(rnd):
        judge["early_gain_vs_random"] = {**diff_runs(early[cur], early[rnd]),
                                         "question": f"{ep} epoch 시점(학습 속도): {cur} - {rnd}"}
    if cur and "random_frames" in runs:
        judge["same_frames"] = {**diff_runs(pooled[cur], pooled["random_frames"]), "question": "같은 프레임 수에서 (선별 - 프레임 맞춘 무작위)"}
    n = sorted({len(v) for v in runs.values()})
    if n == [1]:
        label = "예비 결과 (시드 1개, 롤아웃 기준 95% 신뢰구간)"
    elif len(n) == 1:
        label = f"시드 {n[0]}개 (롤아웃을 합친 95% 신뢰구간 + 모든 시드에서 같은 방향일 때만 차이 있음)"
    else:
        label = f"묶음마다 시드 수가 다름 ({n[0]}~{n[-1]}개, 판정별 n_seeds 확인). 시드 1개인 비교는 예비 결과"
    return {"table": table, "judgement": judge, "label": label}


def collect(run_dir: Path) -> dict:
    plan_path = run_dir / "plan" / "plan.json"
    if not plan_path.exists():
        raise ValueError("학습 계획(plan.json)이 없다. 먼저 prepare를 실행해야 한다")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    own = run_dir / "results" / "results.json"
    stored = RESULTS_STORE / f"{plan['fingerprint']}.json"
    if own.exists():
        results, reused = json.loads(own.read_text(encoding="utf-8")), False
    elif stored.exists():
        results, reused = json.loads(stored.read_text(encoding="utf-8")), True
    else:
        return {"run_id": plan["run_id"], "fingerprint": plan["fingerprint"], "status": "not_trained",
                "detail": "아직 학습 결과가 없다 (코랩 노트북 실행 필요)"}
    if results.get("fingerprint") != plan["fingerprint"]:
        raise ValueError("결과 파일의 지문이 학습 계획과 다르다")
    unknown = set(results["sets"]) - set(plan["sets"])
    if unknown:
        raise ValueError(f"계획에 없는 묶음 결과: {sorted(unknown)}")
    seeds = None
    for f in (run_dir / "results" / "results_seeds.json", RESULTS_STORE / f"{plan['fingerprint']}_seeds.json"):
        if f.exists():
            seeds = json.loads(f.read_text(encoding="utf-8"))
            break
    if seeds and seeds.get("fingerprint") != plan["fingerprint"]:
        raise ValueError("추가 시드 결과의 지문이 학습 계획과 다르다")
    out = {"run_id": plan["run_id"], "fingerprint": plan["fingerprint"],
           "status": "complete" if set(results["sets"]) == set(plan["sets"]) else "partial",
           "reused": reused, "trained_at": results.get("finished_at") or results.get("created_at"),
           "config": results.get("config", plan["config"]), **compare(plan, results, seeds)}
    if seeds:
        out["seeds_trained_at"] = max((r.get("finished_at", "") for r in seeds["runs"].values()), default=None)
    if reused:
        out["note"] = "같은 선별 결과·설정으로 미리 실행한 학습 결과를 불러왔다"
    return out


def save_results(results_path: Path, runs_root: Path) -> Path:
    """코랩 RESULTS_JSON 파일을 해당 실행 폴더(results/results.json)와 지문 저장소에 함께 저장한다."""
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    run_dir = runs_root / results["run_id"]
    plan = json.loads((run_dir / "plan" / "plan.json").read_text(encoding="utf-8"))
    if results.get("mode") != "main":
        raise ValueError("파일럿 결과는 비교표에 쓰지 않는다 (mode가 main이 아님)")
    if results["fingerprint"] != plan["fingerprint"]:
        raise ValueError("결과 지문이 학습 계획과 다르다")
    (run_dir / "results").mkdir(exist_ok=True)
    dst = run_dir / "results" / "results.json"
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    store_results(dst)
    return dst


def save_seed_results(seeds_path: Path, runs_root: Path) -> Path:
    """Kaggle 추가 시드 결과(results_seeds.json)를 실행 폴더와 지문 저장소에 저장한다.
    시드 1과 같은 학습 계획(지문)이어야 하고, 학습 설정은 시드만 달라야 한다."""
    seeds = json.loads(Path(seeds_path).read_text(encoding="utf-8"))
    run_dir = runs_root / seeds["run_id"]
    plan = json.loads((run_dir / "plan" / "plan.json").read_text(encoding="utf-8"))
    if seeds.get("mode") != "seeds":
        raise ValueError("시험 실행(smoke) 결과는 비교표에 쓰지 않는다 (mode가 seeds가 아님)")
    if seeds["fingerprint"] != plan["fingerprint"]:
        raise ValueError("추가 시드 결과의 지문이 학습 계획과 다르다")
    if {k: v for k, v in seeds["config"].items() if k != "seed"} != {k: v for k, v in plan["config"].items() if k != "seed"}:
        raise ValueError("추가 시드의 학습 설정이 계획과 다르다 (시드 외 설정은 같아야 함)")
    bad = [k for k, r in seeds["runs"].items() if r["set"] not in plan["sets"] or r["seed"] == plan["config"].get("seed", 1)]
    if bad:
        raise ValueError(f"계획에 없는 묶음이거나 시드 1과 겹치는 실행: {bad}")
    (run_dir / "results").mkdir(exist_ok=True)
    dst = run_dir / "results" / "results_seeds.json"
    body = json.dumps(seeds, ensure_ascii=False, indent=1)
    dst.write_text(body, encoding="utf-8")
    RESULTS_STORE.mkdir(parents=True, exist_ok=True)
    (RESULTS_STORE / f"{plan['fingerprint']}_seeds.json").write_text(body, encoding="utf-8")
    return dst


def store_results(results_path: Path) -> Path:
    """코랩에서 받은 results.json을 지문 저장소에 등록한다 (다음 대화에서 재사용)."""
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    RESULTS_STORE.mkdir(parents=True, exist_ok=True)
    dst = RESULTS_STORE / f"{results['fingerprint']}.json"
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return dst


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="코랩 학습 결과를 저장하고 비교표를 출력한다")
    p.add_argument("--save", type=Path, help="코랩 RESULTS_JSON을 저장한 파일 (시드 1)")
    p.add_argument("--save-seeds", type=Path, help="Kaggle 추가 시드 결과 results_seeds.json")
    p.add_argument("--runs-root", type=Path, default=Path("C:/curation-data/runs"))
    a = p.parse_args()
    if not (a.save or a.save_seeds):
        p.error("--save 또는 --save-seeds 중 하나는 필요하다")
    dst = save_results(a.save, a.runs_root) if a.save else save_seed_results(a.save_seeds, a.runs_root)
    out = collect(dst.parent.parent)
    print(json.dumps({k: out[k] for k in ("status", "label", "table", "judgement")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
