"""예산 60 기준선 비교 전체 판정 (1차 + 2차, 규칙은 70fe827 그대로).

- 각 기준선마다 curated_60 - 기준선을 같은 위치끼리 짝지어 비교 (train_eval.paired_diff: 신뢰구간이 0을 넘고 세 시드 모두 같은 방향일 때만 차이 있음)
- 시드+위치 부트스트랩 신뢰구간 (robust_ci.analyze)도 함께
- 전체 270 - curated_60: 하락 5%p 이내 확인은 신뢰구간 위쪽 끝 <= 5%p
- 모든 기준선을 표 하나로. "모든 기준선보다 낫다"는 9개 비교가 모두 차이 있음일 때만

사용: python analysis/b60_all.py <results_paired_all.json> <results_main_all.json (200 epoch 결과)> [출력 json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from curation_tools import train_eval as T  # noqa: E402
import robust_ci as R  # noqa: E402

BASELINES = ["random_60", "length_60", "gripper_60", "nolength3_60", "idle_60", "path_60",
             "stratified_random_60", "diversity_60", "longest_60"]


def totals(doc: dict, s: str, main_doc: dict) -> dict:
    rs = sorted((r for r in doc["runs"].values() if r["set"] == s), key=lambda r: r["seed"])
    final = [sum(T._outcomes(r)) for r in rs]
    # 짝지은 비교 파일에는 400 epoch만 있다. 200 epoch(학습 속도, 30회)는 노트북 원래 결과에서 (전체 270은 A라 없음)
    early = [(((main_doc["runs"].get(f"{s}|seed{r['seed']}") or {}).get("by_epoch") or {}).get("200") or {}).get("success") for r in rs]
    n = len(T._outcomes(rs[0]))
    return {"per_seed": final, "success": sum(final), "rollouts": n * len(rs), "rate": round(sum(final) / (n * len(rs)), 4),
            "early_per_seed": early}


def main(path: str, main_path: str, out: str | None = None) -> None:
    doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    main_doc = json.loads(Path(main_path).read_text(encoding="utf-8-sig"))
    rows = []
    for b in BASELINES:
        p = T.paired_diff(doc, "curated_60", b)
        r = R.analyze(doc, "curated_60", b)
        rows.append({"baseline": b, **totals(doc, b, main_doc), "diff": p["diff"], "ci95": p["ci95"], "per_seed_diff": p["per_seed_diff"],
                     "ci95_seed_and_position": r["ci95_seed_and_position"], "verdict": p["verdict"], "note": p.get("note")})
    drop = T.paired_diff(doc, "train", "curated_60")
    rdrop = R.analyze(doc, "train", "curated_60")
    res = {"curated_60": totals(doc, "curated_60", main_doc), "train": totals(doc, "train", main_doc), "rows": rows,
           "drop_vs_full": {**drop, "confirmed": drop["ci95"][1] <= T.MAX_DROP,
                            "ci95_seed_and_position": rdrop["ci95_seed_and_position"]},
           "all_baselines_beaten": all(r["verdict"].startswith("차이 있음") for r in rows)}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if out:
        Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
