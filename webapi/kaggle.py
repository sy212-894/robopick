"""웹의 Kaggle 학습 패널: 대화에서 승인된 학습 계획의 진행 확인, 중단, 이어서 학습 (MVP 12).

학습 시작(launch)은 Dify 흐름이 사람 승인 뒤에 부른다. 웹은 진행을 보고, 사람이 버튼으로 멈추거나 이어서 한다.
Kaggle 호출은 curation_tools.kaggle_runner를 그대로 쓰고, 멈춤·이어서는 도구 서버와 같은 형식으로 실행 기록에 남긴다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

from curation_tools import kaggle_runner as KR

SID_RE = re.compile(r"^[0-9A-Za-z_-]{1,80}$")
RUN_ID_RE = re.compile(r"^R-[0-9A-Za-z_-]{1,60}$")
_gpu_cache: dict = {"t": 0.0, "v": None}


def plan_run_id(events_path: Path, sid: str) -> str | None:
    """이 대화에서 마지막으로 학습 계획을 준비한(prepared) 선별 결과의 run_id."""
    if not SID_RE.match(sid) or not events_path.exists():
        return None
    found = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("session_id") == sid and e.get("event") == "prepared":
            found = e.get("run_id") or found
    return found if found and RUN_ID_RE.match(found) else None


def _run_dir(runs_root: Path, run_id: str) -> Path:
    p = (runs_root / run_id).resolve()
    if p.parent != runs_root.resolve() or not p.is_dir():
        raise ValueError(f"실행 폴더가 없음: {run_id}")
    return p


def gpu(force: bool = False) -> dict:
    """남은 GPU (1분 캐시). 실패하면 이유를 돌려준다."""
    if not force and _gpu_cache["v"] and time.time() - _gpu_cache["t"] < 60:
        return _gpu_cache["v"]
    try:
        v = {"ok": True, **KR.gpu_left_hours()}
    except Exception as e:  # noqa: BLE001  화면에는 이유만 보여 준다
        return {"ok": False, "detail": str(e)[:200]}
    _gpu_cache.update(t=time.time(), v=v)
    return v


def _log(events_path: Path, sid: str, run_id: str, out: dict) -> None:
    st = str(out.get("status"))
    rec = {"ts": dt.datetime.now().isoformat(timespec="milliseconds"), "session_id": sid, "tool": "web",
           "event": st if st.startswith("kaggle_") else f"kaggle_{st}", "run_id": run_id, "detail": out.get("detail") or out.get("slug")}
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def act(stage: str, sid: str, runs_root: Path, events_path: Path) -> dict:
    """stage: status | stop | resume."""
    run_id = plan_run_id(events_path, sid)
    if not run_id:
        return {"status": "no_plan", "detail": "이 대화에는 승인된 학습 계획이 없습니다"}
    run_dir = _run_dir(runs_root, run_id)
    fn = {"status": KR.status, "stop": KR.stop, "resume": KR.resume}[stage]
    try:
        out = fn(run_dir, runs_root)
    except (RuntimeError, ValueError) as e:
        out = {"status": "kaggle_error", "detail": str(e)[:300]}
    if stage != "status":
        _log(events_path, sid, run_id, out)
        _gpu_cache["t"] = 0.0
    out = {**out, "run_id": run_id, "launch_enabled": KR.LAUNCH_ENABLED}
    out["gpu"] = gpu()
    return out
