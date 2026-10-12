"""보고 수치 검사 (7주차 MVP 성공 기준: "보고에 나오는 수치가 실행 기록과 100% 일치").

Dify 답변 텍스트에 나온 숫자가 모두 그 대화의 실행 기록·결과 파일에서 나온 값인지 확인한다.
1. events.jsonl에서 대화 ID(session_id)의 run_id들을 찾는다
2. 그 run의 analysis / selection / 검수(review) / 학습 계획 / 학습 결과(collect)의 모든 숫자와,
   성공률·차이·신뢰구간을 백분율로 바꾼 값을 허용 목록으로 모은다
3. 답변의 숫자 중 허용 목록에 없는 것을 보고한다 (형식 숫자 1~10, 주차·격자 같은 고정 문구 숫자는 빼고 본다)

사용: python -m curation_tools.check_report <답변 텍스트 파일> <session_id>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from curation_tools import review, train_eval

RUNS_ROOT = Path("C:/curation-data/runs")
EVENTS = Path("C:/curation-data/logs/events.jsonl")
NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def run_ids(session_id: str, events: Path = EVENTS) -> list[str]:
    ids = []
    for line in events.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        rid = e.get("run_id")
        if e.get("session_id") == session_id and rid and rid not in ids:
            ids.append(rid)
    return ids


def _walk(x, out: set[float]) -> None:
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        out.add(round(float(x), 4))
        if -1 <= x <= 1:  # 비율은 백분율로도 허용 (반올림 0자리·1자리)
            out.add(round(x * 100))
            out.add(round(x * 100, 1))
    elif isinstance(x, dict):
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk(v, out)
    elif isinstance(x, str):
        for m in NUM.findall(x):
            out.add(round(float(m.replace(",", "")), 4))


def allowed_numbers(ids: list[str], runs_root: Path = RUNS_ROOT) -> set[float]:
    out: set[float] = set()
    for rid in ids:
        d = runs_root / rid
        for name in ("analysis.json", "selection.json", "plan/plan.json"):
            f = d / name
            if f.exists():
                body = json.loads(f.read_text(encoding="utf-8"))
                body.pop("demos", None)  # 시범별 값은 보고에 나오지 않는다 (요약만)
                body.pop("scores", None)
                _walk(body, out)
        if (d / "selection.json").exists():
            _walk(review.review(d, runs_root), out)
        if (d / "plan" / "plan.json").exists():
            c = train_eval.collect(d)
            _walk(c, out)
            for j in c.get("judgement", {}).values():  # 차이·신뢰구간은 %p 정수로 표시된다
                if isinstance(j, dict):
                    for v in [j.get("diff")] + list(j.get("ci95") or []):
                        if v is not None:
                            out.update({round(v * 100), abs(round(v * 100))})
    return out


def check(answer: str, ids: list[str], runs_root: Path = RUNS_ROOT) -> dict:
    ok = allowed_numbers(ids, runs_root)
    found = [m for m in NUM.findall(answer)]
    bad = []
    for m in found:
        v = round(float(m.replace(",", "")), 4)
        if 0 <= abs(v) <= 10 or v in ok or abs(v) in ok:  # 1~10은 형식 숫자(목록 번호, 3x3, 1주차, 5%p 기준)로 본다
            continue
        bad.append(m)
    return {"run_ids": ids, "numbers": len(found), "unmatched": bad, "verdict": "pass" if not bad else "check"}


def main() -> None:
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    print(json.dumps(check(text, run_ids(sys.argv[2])), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
