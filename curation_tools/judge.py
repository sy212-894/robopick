"""사용자가 학습 키트로 학습한 뒤 올린 결과 파일을 판정한다.

결과 파일에 든 묶음으로 나눈다 (규칙은 그동안의 짝지은 비교 그대로, 판정은 코드가 한다):
- 선별과 무작위(또는 전체)가 함께 있으면 → "선별 효과 판정": 같은 시험 위치끼리 짝지은 비교
  (무작위보다 나은지, 전체 대비 하락 5%p 이내인지. train_eval.paired_report)
- 선별만 있으면 → "결과 확인": 성공률과 95% 신뢰구간, 근거표의 비슷한 실험 결과를 나란히. 판정이라는 말을 쓰지 않는다
  (학습이 제대로 돌았는지 점검하는 수준. 같은 계획으로 우리가 한 실험이 있으면 그 성공률과 비교할 수 있다)
결과 파일은 키트 노트북이 만든 형식이어야 한다: 계획 지문이 맞고, 시험마다 시작 위치·행동 난수가 12345+i로 고정
(그래야 우리 실험과 같은 위치끼리 짝지을 수 있다). 사용자 결과는 우리 실험 결과(results.json)를 덮어쓰지 않고 따로 저장한다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from curation_tools import evidence as E
from curation_tools import train_eval as T

RUN_ID_RE = re.compile(r"^R-[0-9A-Za-z_-]{1,60}$")


def _role(sets: set[str]) -> dict[str, str | None]:
    return {"curated": next((s for s in sorted(sets) if s.startswith("curated")), None),
            "random": next((s for s in sorted(sets) if s.startswith("random_") and s != "random_frames"), None),
            "train": "train" if "train" in sets else None}


def validate(doc: dict, runs_root: Path) -> dict:
    """결과 파일 형식과 계획을 확인하고 계획을 돌려준다. 맞지 않으면 이유와 함께 ValueError."""
    for k in ("fingerprint", "run_id", "runs"):
        if k not in doc:
            raise ValueError(f"키트 노트북의 결과 파일이 아니다 ({k} 없음)")
    if doc.get("mode") != "main":
        raise ValueError("학습 결과 파일이 아니다 (mode가 main이 아님)")
    if doc.get("eval_seed") != 12345 or doc.get("policy_seed") != "EVAL_SEED+i":
        raise ValueError("시험 위치·행동 난수가 고정되지 않은 결과라 짝지어 비교할 수 없다")
    if not doc["runs"]:
        raise ValueError("끝난 학습이 하나도 없다")
    plan_path = runs_root / str(doc["run_id"]) / "plan" / "plan.json"
    if not RUN_ID_RE.match(str(doc["run_id"])) or not plan_path.exists():
        raise ValueError(f"이 결과의 학습 계획을 찾을 수 없다 ({doc['run_id']})")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["fingerprint"] != doc["fingerprint"]:
        raise ValueError("결과 파일의 계획 지문이 학습 계획과 다르다 (다른 키트의 결과)")
    final = str(plan["config"]["num_epochs"])
    for key, r in doc["runs"].items():
        if r.get("set") not in plan["sets"]:
            raise ValueError(f"계획에 없는 묶음: {key}")
        if not ((r.get("by_epoch") or {}).get(final) or {}).get("outcomes"):
            raise ValueError(f"{key}에 {final} epoch 시험별 결과가 없다")
        for ep, e in (r.get("by_epoch") or {}).items():
            oc = (e or {}).get("outcomes")
            # 시험 결과는 성공 1, 실패 0만 (다른 값이 섞이면 성공률이 부풀거나 계산이 깨진다)
            if not isinstance(oc, list) or not all(type(v) is int and v in (0, 1) for v in oc):
                raise ValueError(f"{key}의 {ep} epoch 시험 결과가 성공 1, 실패 0의 목록이 아니다")
    return plan


def judge(doc: dict, runs_root: Path) -> dict:
    plan = validate(doc, runs_root)
    final = str(plan["config"]["num_epochs"])
    runs = {k: {"set": r["set"], "seed": r["seed"], "outcomes": r["by_epoch"][final]["outcomes"],
                "success": sum(r["by_epoch"][final]["outcomes"])} for k, r in doc["runs"].items()}
    roles = _role({r["set"] for r in runs.values()})
    rates = {}
    for role, s in roles.items():
        if s:
            o = [x for r in runs.values() if r["set"] == s for x in r["outcomes"]]
            rates[role] = {"set": s, "success": sum(o), "rollouts": len(o), "rate": round(sum(o) / len(o), 4),
                           "ci95": list(T.wilson(sum(o), len(o))), "seeds": sorted(r["seed"] for r in runs.values() if r["set"] == s)}
    budget = len(plan["sets"][roles["curated"]]) if roles["curated"] else None
    out = {"fingerprint": plan["fingerprint"], "run_id": plan["run_id"], "dataset": plan["dataset"]["name"], "budget": budget,
           "epoch": int(final), "platform": doc.get("platform"), "kit": doc.get("kit"), "rates": rates}
    if not roles["curated"]:
        raise ValueError("선별 묶음 결과가 없다")
    if roles["random"] or roles["train"]:
        rep = T.paired_report({"epoch": int(final), "runs": runs})
        n_seeds = len({r["seed"] for r in runs.values()})
        out.update(kind="effect", title="선별 효과 판정", label=rep["label"],
                   gain_vs_random=rep.get("gain_vs_random"), drop_vs_full=rep.get("drop_vs_full"),
                   note=("학습 시드 1개라 시드마다 같은 방향인지는 볼 수 없습니다. 우리 실험(시드 3~5개)보다 약한 근거입니다"
                         if n_seeds == 1 else None),
                   missing=[r for r in ("random", "train") if not roles[r]])
    else:
        out.update(kind="check", title="결과 확인",
                   note="선별 묶음만 학습한 결과라 선별 효과를 판정하지 않습니다. 학습이 제대로 돌았는지 점검하는 수준입니다")
    ev = E.lookup(plan["dataset"]["name"], budget) if budget else {"status": "no_evidence", "rows": []}
    same = [r for r in ev["rows"] if r.get("source", "").startswith(plan["run_id"] + "/") or r.get("source") == plan["run_id"]]
    out["evidence"] = {"status": ev["status"], "same_plan": bool(same),
                       "rows": [{k: r.get(k) for k in ("dataset", "budget", "experiment", "rates", "gain_vs_random", "drop_vs_full")}
                                for r in ev["rows"]]}
    return out


def save(doc: dict, result: dict, runs_root: Path, session_id: str | None = None) -> Path:
    """사용자 결과와 판정을 실행 폴더의 results/uploaded/ 아래에 따로 저장한다 (우리 실험 결과는 그대로)."""
    d = runs_root / result["run_id"] / "results" / "uploaded"
    d.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # 같은 초에 두 번 올려도 덮어쓰지 않게
    (d / f"{stamp}_results.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    p = d / f"{stamp}_judgement.json"
    p.write_text(json.dumps({**result, "session_id": session_id, "judged_at": stamp}, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
