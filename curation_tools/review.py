"""review_selection: select_demos 결과를 실제 파일로 다시 검사한다 (5주차 검수자, 7주차 설계 2-6).

select_demos 안의 검사와 별개로, 저장된 selection.json과 analysis.json만 읽어 규칙을 다시 확인한다.
에이전트(LLM)가 보고한 내용은 보지 않는다. 숙련도 라벨도 쓰지 않는다.

규칙
- budget: 선택 수가 예산 이하인가
- duplicate: 같은 시범이 두 번 들어가지 않았나
- eval_leak: 모든 선택이 train 분할인가 (valid 포함 금지)
- allocation: 칸별 선택 합 = 전체 선택 수, 부족(shortage)이 있으면 보고
- frame_match: random_frames의 총 프레임이 선택 결과와 허용 오차 안인가
- filter_keys: 학습에 쓸 필터 키 복사본이 있는가
"""
from __future__ import annotations

import json
from pathlib import Path

from curation_tools.select_demos import FRAME_TOLERANCE
from curation_tools.train_eval import MINUTES_BY_DATASET, TRAIN_CONFIGS


def review(run_dir: Path, runs_root: Path) -> dict:
    sel = json.loads((run_dir / "selection.json").read_text(encoding="utf-8"))
    analysis = json.loads((runs_root / sel["analysis_run_id"] / "analysis.json").read_text(encoding="utf-8"))
    demos = {d["id"]: d for d in analysis["demos"]}
    ids = sel["selected_ids"]
    budget = sel["budget"]["demos"]
    issues, warnings = [], []

    if len(ids) > budget:
        issues.append({"check": "budget", "detail": f"선택 {len(ids)}개가 예산 {budget}개를 넘음"})
    if len(set(ids)) != len(ids):
        issues.append({"check": "duplicate", "detail": f"중복 {len(ids) - len(set(ids))}개"})
    unknown = [i for i in ids if i not in demos]
    leaked = [i for i in ids if i in demos and demos[i].get("split") != "train"]
    if unknown:
        issues.append({"check": "unknown_id", "detail": f"분석 결과에 없는 ID {len(unknown)}개"})
    if leaked:
        issues.append({"check": "eval_leak", "detail": f"train이 아닌 시범 {len(leaked)}개 포함"})
    if sum(a["selected"] for a in sel["allocation"]) != len(ids):
        issues.append({"check": "allocation", "detail": "칸별 선택 합이 전체 선택 수와 다름"})
    short = [a["condition"] for a in sel["allocation"] if a["shortage"] > 0]
    if short:
        warnings.append({"check": "shortage", "detail": f"후보가 모자란 칸: {short}"})
    frames = sum(demos[i]["length"] for i in ids if i in demos)
    if frames != sel["total_frames"]:
        issues.append({"check": "frames", "detail": f"기록된 총 프레임 {sel['total_frames']}과 실제 합 {frames}이 다름"})
    rf = sel["sets"].get("random_frames", {}).get("total_frames")
    if rf is not None and abs(rf - frames) > frames * FRAME_TOLERANCE:
        issues.append({"check": "frame_match", "detail": f"random_frames {rf} vs 선택 {frames}"})
    # 기준선 묶음도 학습 비교에 쓰이므로 중복과 평가 누수를 같이 검사한다
    for name, s in sel["sets"].items():
        bids = s.get("ids", [])
        if len(set(bids)) != len(bids):
            issues.append({"check": "duplicate", "detail": f"{name}: 중복 {len(bids) - len(set(bids))}개"})
        bad = [i for i in bids if demos.get(i, {}).get("split") != "train"]
        if bad:
            issues.append({"check": "eval_leak", "detail": f"{name}: train이 아닌 시범 {len(bad)}개"})
    strat = next((s for k, s in sel["sets"].items() if k.startswith("stratified_random")), None)
    if strat is not None:
        per = {}
        for i in strat["ids"]:
            c = demos.get(i, {}).get("condition")
            per[c] = per.get(c, 0) + 1
        want = {a["condition"]: a["selected"] for a in sel["allocation"]}
        if per != want:
            issues.append({"check": "stratified", "detail": "조건별 균등 기준선의 칸별 개수가 선택 결과와 다름"})
    # 선별 도구가 자체 검사에서 낸 문제 중 위에서 다시 검사하지 않는 것(예: 칸 안 위치 쏠림)은 경고로 넘긴다.
    # 전에는 검수가 이를 보지 않아 선별은 revise인데 승인 화면에는 pass·문제 없음으로 나왔다 (2026-10-12 Square에서 발견).
    # 위치 쏠림 기준은 칸 하나 기준(무작위 95%)이라 9칸을 함께 보면 무작위로도 한 칸쯤 넘기 쉬워, 승인을 막지 않고 경고로 둔다
    rechecked = {"budget", "duplicate", "unknown_id", "eval_leak", "allocation", "frames", "frame_match", "stratified", "filter_keys"}
    for i in (sel.get("checks") or {}).get("issues", []):
        if i.get("check") not in rechecked:
            warnings.append({"check": i.get("check"), "detail": f"선별 도구 검사: {i.get('detail')}"})
    copy = (sel.get("hdf5") or {}).get("path")
    if not (copy and Path(copy).exists()) and not list(run_dir.glob("*_curated.hdf5")):
        issues.append({"check": "filter_keys", "detail": "필터 키 복사본 없음"})

    sets = {k: {"n_demos": v["n_demos"], "total_frames": v["total_frames"]} for k, v in sel["sets"].items()}
    plan_sets = list(sets) + ["train"]  # 학습 비교 묶음: 선택 결과, 무작위 2종, 전체
    train_ids = [d for d in analysis["demos"] if d.get("split") == "train"]
    name = analysis["dataset"].get("name", "can_mh")
    cfg = TRAIN_CONFIGS.get(name, TRAIN_CONFIGS["can_mh"])
    minutes = MINUTES_BY_DATASET.get(name, MINUTES_BY_DATASET["can_mh"])
    where = "코랩 T4 본 실험 측정" if name == "can_mh" else "Kaggle T4 파일럿 측정"
    note = f"{where} 기준(묶음당 약 {minutes}분), {cfg['algo'].upper()} {cfg['num_epochs']} epoch, 시드 1개"
    return {
        "run_id": sel["run_id"],
        "analysis_run_id": sel["analysis_run_id"],
        "verdict": "pass" if not issues else "revise",
        "issues": issues,
        "warnings": warnings,
        "budget": budget,
        "selected": {"n_demos": len(ids), "total_frames": frames},
        "dataset": name,
        "sets": sets,
        "train_set": {"n_demos": len(train_ids), "total_frames": int(sum(d["length"] for d in train_ids))},
        "training_plan": {"filter_keys": plan_sets, "n_sets": len(plan_sets),
                          "algo": cfg["algo"], "num_epochs": cfg["num_epochs"],
                          "est_minutes": len(plan_sets) * minutes, "note": note},
    }
