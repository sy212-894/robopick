"""예산 135개 실험(B)의 짝지은 비교 파일을 만든다.

B 노트북은 선별 135와 무작위 135만 학습했다. 1주차 기준 "전체 대비 하락 5%p 이내"를 보려면 전체 270이 필요해서,
Can 최종 평가(A)의 전체 270 결과를 같은 위치끼리 짝지어 붙인다. 붙여도 되는 조건을 먼저 검사한다:
평가 위치·행동 난수 고정 방식, 시험 수, 400 epoch 시점, 학습 설정(평가 횟수 제외), 데이터 파일, 전체 270 묶음 구성이 같아야 한다.

사용: python kaggle/combine_budget_paired.py <B results_main.json> <A results_paired.json> <출력 파일>
그다음: python -m curation_tools.train_eval --save-paired <출력 파일>
"""
import json
import sys
from pathlib import Path

RUNS = Path("C:/curation-data/runs")


def main(b_path: str, a_path: str, out_path: str) -> None:
    b = json.loads(Path(b_path).read_text(encoding="utf-8-sig"))
    a = json.loads(Path(a_path).read_text(encoding="utf-8-sig"))
    pb = json.loads((RUNS / b["run_id"] / "plan" / "plan.json").read_text(encoding="utf-8"))
    pa = json.loads((RUNS / a["run_id"] / "plan" / "plan.json").read_text(encoding="utf-8"))
    epoch = str(b["config"]["num_epochs"])

    checks = {
        "B 결과와 B 계획의 지문": b["fingerprint"] == pb["fingerprint"],
        "A 결과와 A 계획의 지문": a["fingerprint"] == pa["fingerprint"],
        "평가 위치 난수": a["eval_seed"] == b["eval_seed"],
        "행동 난수 고정": a["policy_seed"] == b["policy_seed"] == "EVAL_SEED+i",
        "평가 시점": str(a["epoch"]) == epoch,
        "학습 설정 (평가 횟수 제외)": {k: v for k, v in pa["config"].items() if k != "rollout_n"}
                                == {k: v for k, v in pb["config"].items() if k != "rollout_n"},
        "데이터 파일": pa["dataset"]["sha256"] == pb["dataset"]["sha256"],
        "전체 270 묶음 구성": pa["sets"]["train"] == pb["sets"]["train"],
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise SystemExit(f"합칠 수 없다: {bad}")

    runs = {}
    for k, r in b["runs"].items():
        o = r["by_epoch"][epoch]["outcomes"]
        runs[k] = {"set": r["set"], "seed": r["seed"], "outcomes": o, "success": sum(o), "source": "B"}
    n = {len(r["outcomes"]) for r in runs.values()}
    for k, r in a["runs"].items():
        if r["set"] == "train":
            if len(r["outcomes"]) not in n:
                raise SystemExit("A 전체 270의 시험 수가 B와 다르다")
            runs[k] = {"set": "train", "seed": r["seed"], "outcomes": r["outcomes"], "success": r["success"],
                       "source": f"A ({a['run_id']}, 지문 {a['fingerprint']})"}

    out = {"fingerprint": b["fingerprint"], "run_id": b["run_id"], "mode": "paired", "eval_seed": b["eval_seed"],
           "policy_seed": b["policy_seed"], "epoch": int(epoch), "rollouts": n.pop(), "horizon": b["config"]["rollout_horizon"],
           "note": "선별·무작위 135는 B 노트북, 전체 270은 A 최종 평가의 같은 모델·같은 위치 결과", "checks": list(checks),
           "runs": runs}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"검사 통과 {len(checks)}개, 실행 {len(runs)}개 → {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
