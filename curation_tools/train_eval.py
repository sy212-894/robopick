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
DATASET = {"name": "can_mh", "hf_repo": "robomimic/robomimic_datasets", "hf_path": "v1.5/can/mh/low_dim_v15.hdf5"}
# 파일럿(5-4) 결과로 확정한다. LLM이 바꾸지 못하도록 도구 인자로 받지 않는다
TRAIN_CONFIG = {"algo": "bc", "num_epochs": 200, "steps_per_epoch": 100, "batch_size": 100,
                "seed": 1, "rollout_n": 50, "rollout_horizon": 400}
MINUTES_PER_SET = 30  # 파일럿 측정 후 갱신
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


def fingerprint(sets: dict[str, list[str]], config: dict, data_sha: str) -> str:
    body = json.dumps({"sets": {k: sorted(v) for k, v in sorted(sets.items())}, "config": config, "data": data_sha},
                      sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def prepare(run_dir: Path, runs_root: Path, config: dict | None = None) -> dict:
    config = dict(config or TRAIN_CONFIG)
    sel = json.loads((run_dir / "selection.json").read_text(encoding="utf-8"))
    analysis = json.loads((runs_root / sel["analysis_run_id"] / "analysis.json").read_text(encoding="utf-8"))
    sets = {name: s["ids"] for name, s in sel["sets"].items()}
    sets["train"] = sorted((d["id"] for d in analysis["demos"] if d.get("split") == "train"),
                           key=lambda s: int(s.split("_")[1]))
    fp = fingerprint(sets, config, analysis["dataset"]["sha256"])
    plan = {"run_id": sel["run_id"], "analysis_run_id": sel["analysis_run_id"], "fingerprint": fp,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "dataset": {**DATASET, "sha256": analysis["dataset"]["sha256"]},
            "config": config, "order": _order(list(sets)), "sets": sets}
    out = run_dir / "plan"
    out.mkdir(exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return {"run_id": sel["run_id"], "fingerprint": fp, "status": "prepared",
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


def compare(plan: dict, results: dict) -> dict:
    sets = results["sets"]
    table = []
    for name in plan["order"]:
        r = sets.get(name)
        row = {"set": name, "n_demos": len(plan["sets"][name])}
        if r:
            row.update({"success": r["success"], "rollouts": r["rollouts"],
                        "success_rate": round(r["success"] / r["rollouts"], 4),
                        "ci95": wilson(r["success"], r["rollouts"]),
                        "train_min": round(r.get("train_sec", 0) / 60, 1)})
        else:
            row["status"] = "결과 없음"
        table.append(row)
    cur = next((n for n in sets if n.startswith("curated")), None)
    rnd = next((n for n in sets if n.startswith("random_") and n != "random_frames"), None)
    strat = next((n for n in sets if n.startswith("stratified")), None)
    judge = {}
    train = sets.get("train")
    if train and train["success"] / train["rollouts"] < MIN_TRAIN_SUCCESS:
        judge["validity"] = f"판정 불가: 전체 데이터 기준선 성공률이 {MIN_TRAIN_SUCCESS:.0%} 미만 (학습 설정 문제)"
    if cur and rnd:
        d = diff(sets[cur], sets[rnd])
        judge["gain_vs_random"] = {**d, "target": TARGET_GAIN, "meets_target_point": d["diff"] >= TARGET_GAIN,
                                   "question": f"{cur}가 {rnd}보다 {TARGET_GAIN:.0%}p 이상 높은가"}
    if cur and train:
        d = diff(sets["train"], sets[cur])
        judge["drop_vs_full"] = {**d, "target": MAX_DROP, "meets_target_point": d["diff"] <= MAX_DROP,
                                 "confirmed": d["ci95"][1] <= MAX_DROP,
                                 "question": f"전체 대비 {cur}의 하락이 {MAX_DROP:.0%}p 이내인가"}
    if strat and rnd:
        judge["effect_allocation"] = {**diff(sets[strat], sets[rnd]), "question": "칸별 배분의 효과 (조건별 균등 - 무작위)"}
    if cur and strat:
        judge["effect_quality"] = {**diff(sets[cur], sets[strat]), "question": "품질 점수의 효과 (선별 - 조건별 균등)"}
    if cur and "random_frames" in sets:
        judge["same_frames"] = {**diff(sets[cur], sets["random_frames"]), "question": "같은 프레임 수에서 (선별 - 프레임 맞춘 무작위)"}
    seeds = results.get("config", {}).get("n_seeds", 1)
    return {"table": table, "judgement": judge,
            "label": "예비 결과 (시드 1개, 롤아웃 기준 95% 신뢰구간)" if seeds == 1 else f"시드 {seeds}개"}


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
    out = {"run_id": plan["run_id"], "fingerprint": plan["fingerprint"],
           "status": "complete" if set(results["sets"]) == set(plan["sets"]) else "partial",
           "reused": reused, "trained_at": results.get("finished_at") or results.get("created_at"),
           "config": results.get("config", plan["config"]), **compare(plan, results)}
    if reused:
        out["note"] = "같은 선별 결과·설정으로 미리 실행한 학습 결과를 불러왔다"
    return out


def store_results(results_path: Path) -> Path:
    """코랩에서 받은 results.json을 지문 저장소에 등록한다 (다음 대화에서 재사용)."""
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    RESULTS_STORE.mkdir(parents=True, exist_ok=True)
    dst = RESULTS_STORE / f"{results['fingerprint']}.json"
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return dst
