"""짝지은 비교의 신뢰구간을 학습 시드·시험 위치 흔들림까지 넣어 다시 계산한다 (한계 6·7).

train_eval.paired_diff는 짝 300개(시드 3 x 위치 100)를 서로 독립으로 보고 신뢰구간을 낸다. 실제로는
같은 모델 3개에 묶인 시험이고 위치도 모든 묶음이 공유해서, 신뢰구간이 실제 흔들림보다 좁다. 여기서는:
- 위치 부트스트랩: 위치 100개를 복원 추출하고, 뽑힌 위치는 모든 시드·묶음에서 함께 쓴다 (위치 운 반영)
- 시드+위치 부트스트랩: 시드도 복원 추출 (학습 흔들림 반영). 시드가 3개라 서로 다른 조합이 10개뿐이어서 대략적인 값이다
- 반으로 나눈 비교: 위치 1~50번과 51~100번의 차이를 따로 낸다

사용: python analysis/robust_ci.py <results_paired.json> [<results_paired.json> ...] (결과는 JSON으로 출력)
"""
import json
import random
import sys
from pathlib import Path

B = 10000          # 부트스트랩 반복 수
SEED = 20261013    # 부트스트랩 난수 (결과 재현용)


def outcomes(doc: dict) -> dict[str, dict[int, list[int]]]:
    out: dict[str, dict[int, list[int]]] = {}
    for r in doc["runs"].values():
        out.setdefault(r["set"], {})[r["seed"]] = r["outcomes"]
    return out


def diff(o: dict, a: str, b: str, seeds: list[int], pos: list[int]) -> float:
    s = sum(o[a][sd][p] - o[b][sd][p] for sd in seeds for p in pos)
    return s / (len(seeds) * len(pos))


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]


def analyze(doc: dict, a: str, b: str) -> dict:
    o = outcomes(doc)
    seeds = sorted(set(o[a]) & set(o[b]))
    n = len(o[a][seeds[0]])
    pos = list(range(n))
    rng = random.Random(SEED)
    by_pos, by_both = [], []
    for _ in range(B):
        p = [rng.randrange(n) for _ in pos]
        by_pos.append(diff(o, a, b, seeds, p))
        s = [rng.choice(seeds) for _ in seeds]
        by_both.append(diff(o, a, b, s, p))
    half = n // 2
    return {
        "compare": f"{a} - {b}", "n_seeds": len(seeds), "n_positions": n,
        "diff": round(diff(o, a, b, seeds, pos), 4),
        "ci95_position": [round(pct(by_pos, 0.025), 4), round(pct(by_pos, 0.975), 4)],
        "ci95_seed_and_position": [round(pct(by_both, 0.025), 4), round(pct(by_both, 0.975), 4)],
        "first_half": round(diff(o, a, b, seeds, list(range(half))), 4),
        "second_half": round(diff(o, a, b, seeds, list(range(half, n))), 4),
        "per_seed": {sd: round(diff(o, a, b, [sd], pos), 4) for sd in seeds},
    }


def pairs(doc: dict) -> list[tuple[str, str]]:
    sets = {r["set"] for r in doc["runs"].values()}
    cur = next((s for s in sorted(sets) if s.startswith("curated")), None)
    rnd = next((s for s in sorted(sets) if s.startswith("random_") and s != "random_frames"), None)
    strat = next((s for s in sorted(sets) if s.startswith("stratified")), None)
    want = [(cur, rnd), ("train", cur), (cur, strat), (strat, rnd), (cur, "random_frames")]
    return [(a, b) for a, b in want if a in sets and b in sets]


def main(paths: list[str]) -> None:
    report = {}
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        report[f"{doc['run_id']} ({doc['fingerprint']})"] = [analyze(doc, a, b) for a, b in pairs(doc)]
    print(json.dumps({"bootstrap": B, "seed": SEED, "results": report}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
