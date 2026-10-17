"""suggest_datasets: 학습 목적 문장으로 데이터셋 후보를 고른다 (데이터가 없는 사용자를 위한 입구).

판단은 코드가 한다 (LLM은 결과를 설명만 한다).
1. 작업: 목적 문장의 동작·물체 낱말을 목록(catalog.json)의 keywords와 맞춰 점수를 매긴다
2. 데이터 종류: "깨끗한·전문가·숙련"이면 PH, "강화학습·자동"이면 MG, "좋은·나쁜 쌍"이면 Paired, 아무 말이 없으면 MH를 먼저
   (MH는 숙련도가 섞여 있어 선별할 의미가 있고, 이 에이전트가 실험으로 검증한 종류)
3. 같은 점수면 이 에이전트에서 실제로 해 본 데이터(tested, 확인 학습 가능)를 앞에 둔다
맞는 낱말이 하나도 없으면 추측하지 않고 고를 수 있는 작업 목록을 돌려준다.
"""
from __future__ import annotations

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
TYPE_WORDS = {
    "ph": ("깨끗", "전문가", "숙련", "한 명", "proficient", "expert", "clean"),
    "mg": ("강화학습", "자동", "기계", "생성된", "machine", "rl", "sac"),
    "paired": ("좋은", "나쁜", "쌍", "paired"),
    "mh": ("여러 사람", "여러 명", "섞인", "품질", "선별", "multi", "mixed", "curation"),
}
SUPPORT_RANK = {"tested": 0, "untested": 1, "unsupported": 2}


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _type_pref(goal: str) -> str | None:
    hits = {t: sum(w in goal for w in words) for t, words in TYPE_WORDS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] else None


def suggest(goal: str, n: int = 3, catalog: dict | None = None) -> dict:
    cat = catalog or load_catalog()
    g = goal.lower()
    pref = _type_pref(g)
    scored = []
    for d in cat["datasets"]:
        matched = [k for k in d["keywords"] if k.lower() in g]
        if not matched:
            continue
        type_ok = d["type"] == (pref or "mh")
        scored.append((len(matched), type_ok, -SUPPORT_RANK[d["support"]], d, matched))
    if not scored:
        tasks = sorted({d["task"]: d["summary"] for d in cat["datasets"]}.items())
        return {"status": "no_match", "goal": goal,
                "detail": "목적 문장에서 작업을 알아볼 낱말을 찾지 못했다. 아래 작업 중 무엇에 가까운지 다시 묻는다",
                "tasks": [{"task": t, "summary": s} for t, s in tasks], "sources": cat["sources"]}
    scored.sort(key=lambda x: (-x[0], not x[1], -x[2], x[3]["id"]))
    out = []
    for score, type_ok, _, d, matched in scored[:n]:
        reasons = [f"목적 문장의 '{', '.join(matched)}'가 {d['task']} 작업({d['summary']})과 맞음"]
        reasons.append(f"데이터 종류 {d['type'].upper()}: {cat['types'][d['type']]}")
        if pref and type_ok:
            reasons.append("요청한 데이터 종류와 맞음")
        out.append({"id": d["id"], "task": d["task"], "type": d["type"], "demos": d["demos"], "arms": d["arms"],
                    "summary": d["summary"], "summary_source": d.get("summary_source"),
                    "support": d["support"], "support_note": cat["support_note"][d["support"]], "verify": d["verify"],
                    "hf_path": d["hf_path"], "reasons": reasons})
    return {"status": "ok", "goal": goal, "type_preference": pref or "mh (기본: 숙련도가 섞여 선별할 의미가 있음)",
            "candidates": out, "sources": cat["sources"],
            "next": "후보 중 하나를 고르면 그 데이터로 분석·진단을 시작한다. support가 tested인 데이터만 바로 분석할 수 있다"}
