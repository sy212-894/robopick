"""규칙 점검: 선별 규칙(품질 점수)이 이 데이터에서도 숙련자 시범을 앞에 두는지, 숙련도 라벨로 확인한다 (학습 없이 몇 초).

학습 실험(근거표)이 없는 데이터에서 "막 고른 것인지" 대신 "규칙이 이 데이터에서도 맞는지"를 보여 준다.
라벨은 여기서만 쓰고 선별에는 쓰지 않는다 (선별 결과는 이 점검과 무관하게 같다).

판정 규칙 (2026-10-17, Lift·사용자 파일 결과를 보기 전에 커밋):
- 대상: 선별 후보(train) 중 숙련도 라벨(worse/okay/better)이 있는 시범. 30개 미만이거나 라벨 종류가 하나뿐이면 "점검 불가"
- 품질 점수(선별과 같은 계산, 낮을수록 좋음)와 숙련도(worse 0, okay 1, better 2)의 스피어만 순위 상관
- 95% 신뢰구간: 시범을 다시 뽑는 부트스트랩 2000번 (시드 0)
  - 위쪽 끝 < 0 → "통과" (점수가 좋을수록 숙련자 시범)
  - 아래쪽 끝 > 0 → "반대" (규칙이 이 데이터에서 거꾸로 작동)
  - 그 밖 → "불분명"
- 신호 4개도 같은 방식으로 따로 보고한다 (보고만, 판정은 품질 점수 하나로)
- 통과해도 "학습이 나아진다"는 뜻은 아니다. 학습 효과는 근거표(학습 실험)나 비교 학습 노트북으로만 확인된다
"""
from __future__ import annotations

import numpy as np

from curation_tools.analyze import spearman
from curation_tools.select_demos import SCORE_SIGNALS, candidates, quality_scores

LEVEL = {"worse": 0, "okay": 1, "better": 2}
MIN_LABELED = 30
N_BOOT = 2000
SIGNAL_NAMES = {"length": "길이", "idle_ratio": "멈춤 비율", "path_length": "이동 경로 길이", "gripper_switches": "그리퍼 여닫기 횟수"}
RULE = ("선별 후보 중 라벨 있는 시범에서 품질 점수와 숙련도의 순위 상관, 부트스트랩 95% 신뢰구간 위쪽 끝 < 0이면 통과, "
        "아래쪽 끝 > 0이면 반대, 그 밖은 불분명 (2026-10-17, Lift 결과 전에 정함)")


def _corr_ci(x: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> tuple[float, list[float]]:
    rho = spearman(x, y)
    n, boots = len(x), []
    for _ in range(N_BOOT):
        i = rng.integers(0, n, n)
        if len(np.unique(y[i])) > 1 and len(np.unique(x[i])) > 1:
            boots.append(spearman(x[i], y[i]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return round(rho, 3), [round(float(lo), 3), round(float(hi), 3)]


def _verdict(ci: list[float]) -> str:
    return "통과" if ci[1] < 0 else "반대" if ci[0] > 0 else "불분명"


def check(demos: list[dict], seed: int = 0) -> dict:
    pool = candidates(demos)
    labeled = [d for d in pool if d.get("quality") in LEVEL]
    if len(labeled) < MIN_LABELED or len({d["quality"] for d in labeled}) < 2:
        why = "숙련도 라벨이 없어" if not labeled else f"라벨 있는 시범이 {len(labeled)}개뿐이거나 라벨 종류가 하나라"
        return {"status": "no_labels", "verdict": "점검 불가", "rule": RULE,
                "note": f"{why} 규칙 점검을 할 수 없습니다. 선별은 같은 규칙으로 했지만 이 데이터에서 맞는지는 확인되지 않았습니다"}
    rng = np.random.default_rng(seed)
    scores = quality_scores(pool)  # 선별과 같은 점수 (후보 전체 기준 순위)
    y = np.array([LEVEL[d["quality"]] for d in labeled], float)
    rho, ci = _corr_ci(np.array([scores[d["id"]] for d in labeled]), y, rng)
    signals = []
    for s in SCORE_SIGNALS:
        r, c = _corr_ci(np.array([d[s] for d in labeled], float), y, rng)
        signals.append({"signal": s, "name": SIGNAL_NAMES[s], "spearman": r, "ci95": c, "verdict": _verdict(c)})
    # 점수 상위 절반과 하위 절반의 숙련도 구성 (사람이 읽기 쉬운 보조 숫자)
    ranked = sorted(labeled, key=lambda d: scores[d["id"]])
    half = len(ranked) // 2
    share = lambda ds, q: round(sum(d["quality"] == q for d in ds) / len(ds), 3)
    halves = {"top": {q: share(ranked[:half], q) for q in LEVEL}, "bottom": {q: share(ranked[half:], q) for q in LEVEL}}
    verdict = _verdict(ci)
    note = {"통과": "점수가 좋은 시범일수록 숙련자 시범이었습니다. 선별 규칙이 이 데이터에서도 맞게 작동합니다",
            "반대": "점수가 좋은 시범일수록 서툰 시범이었습니다. 이 데이터에는 선별 규칙이 맞지 않으니 선별 결과를 쓰지 않는 것이 좋습니다",
            "불분명": "점수와 숙련도의 관계가 뚜렷하지 않습니다. 선별 규칙이 이 데이터에서 맞는지 확인되지 않았습니다"}[verdict]
    return {"status": "checked", "verdict": verdict, "rule": RULE, "n_labeled": len(labeled),
            "score_spearman": rho, "ci95": ci, "halves": halves, "signals": signals,
            "note": note + ". 학습이 나아지는지는 학습 실험으로만 확인됩니다"}
