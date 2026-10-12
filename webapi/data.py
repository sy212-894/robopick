"""파일에서 읽는 화면용 데이터: 실행 기록, 소개 페이지, 실험 결과, 근거 문서, 보고 수치 검사.

숫자는 모두 결과·기록 파일과 기존 도구(train_eval, check_report)에서 계산한다. 화면에서 새로 만드는 숫자는 없다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from curation_tools import check_report, train_eval

# 화면에 보이는 실험 (run_id). 새 실험을 붙이면 여기에 더한다
CAN_MAIN = "R-20261011-select-main"
CAN_ANALYSIS = "R-20261011-analyze01"
CAN_BUDGET = "R-20261012-select-b135"
SQUARE = "R-20261012-square-select"


# ---------- 실행 기록 (events.jsonl) ----------

def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def runs(events_path: Path, limit: int = 50) -> list[dict]:
    """대화(session_id)별 요약. 최근 것부터."""
    sess: dict[str, dict] = {}
    for e in _events(events_path):
        sid = e.get("session_id")
        if not sid:
            continue
        s = sess.setdefault(sid, {"session_id": sid, "start": e["ts"], "end": e["ts"], "dataset": None, "budget": None,
                                  "review": None, "approval": None, "selection_run": None, "plan": None, "n_events": 0})
        s["end"] = e["ts"]
        s["n_events"] += 1
        args = e.get("args") or {}
        s["dataset"] = args.get("dataset") or s["dataset"]
        s["budget"] = args.get("budget") or s["budget"]
        rid = e.get("run_id") or ""
        if "select" in rid:
            s["selection_run"] = rid
        if e.get("event") == "review":
            s["review"] = e.get("verdict")
        if e.get("agent_event") in ("approved", "rejected"):
            s["approval"] = e["agent_event"]
        if e.get("event") == "prepared":
            s["plan"] = e.get("fingerprint")
    for s in sess.values():
        if s["review"] == "pass" and not s["approval"] and s["selection_run"]:
            s["approval"] = "waiting"
        if not s["dataset"] and s["selection_run"]:
            s["dataset"] = "square_mh" if "square" in s["selection_run"] else None
    rows = sorted(sess.values(), key=lambda s: s["start"], reverse=True)
    return rows[:limit]


def run_detail(events_path: Path, session_id: str) -> dict | None:
    evs = [e for e in _events(events_path) if e.get("session_id") == session_id]
    if not evs:
        return None
    t0 = dt.datetime.fromisoformat(evs[0]["ts"])
    out = []
    for e in evs:
        t = (dt.datetime.fromisoformat(e["ts"]) - t0).total_seconds()
        out.append({"ts": e["ts"], "t": round(t, 3), "tool": e.get("tool"), "event": e.get("event"),
                    "duration_sec": e.get("duration_sec"), "run_id": e.get("run_id"),
                    "detail": e.get("detail") or e.get("verdict") or e.get("fingerprint") or e.get("agent_event")})
    return {"session_id": session_id, "events": out, "raw": evs}


# ---------- 소개 페이지 ----------

def overview(runs_root: Path) -> dict:
    a = json.loads((runs_root / CAN_ANALYSIS / "analysis.json").read_text(encoding="utf-8"))
    s = json.loads((runs_root / CAN_MAIN / "selection.json").read_text(encoding="utf-8"))
    sel = set(s["selected_ids"])
    tr = [d for d in a["demos"] if d.get("split") == "train"]
    xs, ys = [d["init_x"] for d in tr], [d["init_y"] for d in tr]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    nx = lambda v: round((v - x0) / (x1 - x0) * 100, 1)  # noqa: E731
    ny = lambda v: round((v - y0) / (y1 - y0) * 100, 1)  # noqa: E731
    cd = a["condition_definition"]
    by_q: dict[str, list[int]] = {}
    for d in tr:
        by_q.setdefault(d["quality"], []).append(d["length"])
    lengths = {q: {"min": min(v), "max": max(v), "mean": round(sum(v) / len(v))} for q, v in by_q.items()}
    signals = [{"name": k, "spearman": v["spearman_with_skill"], "used": k in s["settings"]["score_signals"]}
               for k, v in a["signal_vs_quality"].items()]
    signals.sort(key=lambda g: abs(g["spearman"]), reverse=True)
    return {
        "dataset": a["dataset"].get("name", "can_mh"),  # Square 지원 전에 만든 Can 분석에는 name이 없다
        "points": [[nx(d["init_x"]), ny(d["init_y"]), 1 if d["id"] in sel else 0] for d in tr],
        "x_edges": [nx(v) for v in cd["x_edges"]], "y_edges": [ny(v) for v in cd["y_edges"]],
        "selected": {"n_demos": len(sel), "total_frames": s["total_frames"]},
        "train": {"n_demos": len(tr), "total_frames": sum(d["length"] for d in tr)},
        "composition": s["validation_only"]["quality_breakdown"],
        "signals": signals, "lengths": lengths,
    }


# ---------- 실험 결과 ----------

def _collect(runs_root: Path, run_id: str) -> dict:
    d = runs_root / run_id
    if not (d / "plan" / "plan.json").exists():
        return {"run_id": run_id, "status": "no_plan"}
    try:
        return train_eval.collect(d)
    except (ValueError, FileNotFoundError) as e:
        return {"run_id": run_id, "status": "error", "detail": str(e)}


def _paired(runs_root: Path, run_id: str) -> dict | None:
    f = runs_root / run_id / "results" / "results_paired.json"
    if not f.exists():
        return None
    doc = json.loads(f.read_text(encoding="utf-8-sig"))
    rep = train_eval.paired_report(doc)
    rep["rates"] = {}
    for r in doc["runs"].values():
        agg = rep["rates"].setdefault(r["set"], {"success": 0, "rollouts": 0, "seeds": 0})
        agg["success"] += r["success"]
        agg["rollouts"] += len(r["outcomes"])
        agg["seeds"] += 1
    return rep


def results(runs_root: Path) -> dict:
    return {
        "can": {**_collect(runs_root, CAN_MAIN), "paired": _paired(runs_root, CAN_MAIN)},
        "can_budget": _collect(runs_root, CAN_BUDGET),
        "square": _collect(runs_root, SQUARE),
    }


# ---------- 근거 문서 (지식베이스 원본) ----------

_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = _FRONT.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        text = text[m.end():]
    # 청크마다 붙인 출처 줄([제목 | 종류 | URL])은 화면에선 빼고 본문만 보여준다
    body = "\n".join(ln for ln in text.splitlines() if not (ln.startswith("[") and ln.rstrip().endswith("]") and "http" in ln))
    return {"file": path.name, "title": meta.get("title", path.stem), "source_url": meta.get("source_url"),
            "doc_type": meta.get("doc_type"), "category": meta.get("category"), "retrieved": meta.get("retrieved"),
            "content": body.strip()}


def docs(kb_dir: Path) -> list[dict]:
    return [{k: v for k, v in _parse_doc(p).items() if k != "content"} for p in sorted(kb_dir.glob("*.md"))]


def doc(kb_dir: Path, name: str) -> dict | None:
    if "/" in name or "\\" in name or ".." in name:
        return None
    p = kb_dir / name
    if p.suffix != ".md" or not p.exists():
        return None
    return _parse_doc(p)


def evidence(node_outputs: dict, kb_dir: Path) -> list[dict]:
    """근거 검색(knowledge-retrieval) 노드 출력 → 화면용 근거 문서 목록.

    우리 흐름은 검색 결과를 코드 노드로 에이전트 지시문에 넣어서 Dify 기본 인용(retriever_resources)이 비어 있다.
    그래서 노드 출력에서 문서 이름·점수·문단을 꺼내고, 지식베이스 원본의 제목·출처 주소를 붙인다.
    """
    out = []
    for r in node_outputs.get("result") or []:
        meta = r.get("metadata") or {}
        name = meta.get("document_name") or r.get("title") or ""
        lines = (r.get("content") or "").splitlines()
        section = lines[0].strip() if lines else ""
        chunk = "\n".join(ln for ln in lines[1:] if not (ln.startswith("[") and "http" in ln)).strip()
        src = doc(kb_dir, name) or {}
        out.append({"file": name, "title": src.get("title", name), "source_url": src.get("source_url"),
                    "doc_type": src.get("doc_type"), "retrieved": src.get("retrieved"),
                    "score": meta.get("score"), "section": section, "chunk": chunk})
    return out


# ---------- 보고 수치 검사 ----------

def check(answer: str, events_path: Path, session_id: str, runs_root: Path) -> dict:
    ids = check_report.run_ids(session_id, events_path)
    if not ids:
        return {"verdict": "no_runs", "detail": "이 대화의 실행 기록이 없습니다", "run_ids": []}
    return check_report.check(answer, ids, runs_root)
