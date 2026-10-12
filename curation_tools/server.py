"""curation-tools MCP 서버: analyze_data, select_demos, review_selection, train_evaluate, log_event를 Dify 같은 MCP 클라이언트에 도구로 제공한다.

- 주소: http://127.0.0.1:8800/mcp (Dify 컨테이너에서는 http://host.docker.internal:8800/mcp)
- 도구 인자는 LLM이 정하므로 파일 경로를 직접 받지 않는다. 데이터는 이름(DATASETS)으로만 고르고,
  run_id는 형식을 검사한 뒤 RUNS_ROOT 바로 아래 폴더만 읽는다.
- LLM에는 요약본만 돌려준다 (시범 ID 목록, 숙련도 라벨 제외).
- 모든 도구 호출은 자동으로 EVENTS_PATH에 기록된다 (시작, 끝, 걸린 시간, 인자, 성공 여부).

실행: python -m curation_tools.server
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from curation_tools import analyze as A
from curation_tools import review as R
from curation_tools import select_demos as S
from curation_tools import train_eval as T

HOST, PORT = "127.0.0.1", 8800
DATASETS = {"can_mh": Path("C:/curation-data/raw/can_mh_low_dim.hdf5"),
            "square_mh": Path("C:/curation-data/raw/square_mh_low_dim.hdf5")}
RUNS_ROOT = A.DEFAULT_OUT_ROOT
EVENTS_PATH = Path("C:/curation-data/logs/events.jsonl")
RUN_ID_RE = re.compile(r"^R-[0-9A-Za-z_-]{1,60}$")
SESSION_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,80}$")
MAX_DETAIL = 2000

# DNS 리바인딩 방어는 켜 두고, Dify 컨테이너가 쓰는 host.docker.internal만 허용 목록에 추가 (0단계에서 확인)
security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "host.docker.internal:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://host.docker.internal:*"],
)
mcp = FastMCP("curation-tools", host=HOST, port=PORT, transport_security=security)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="milliseconds")


def _new_run_id(kind: str) -> str:
    return f"R-{dt.datetime.now():%Y%m%d-%H%M%S}-{kind}-{uuid.uuid4().hex[:4]}"


def _check_session(session_id: str | None) -> str | None:
    if session_id is not None and not SESSION_ID_RE.match(session_id):
        raise ValueError("session_id는 영문, 숫자, -, _ 80자 이내만 허용한다")
    return session_id


def _run_dir(run_id: str) -> Path:
    """run_id 형식을 검사하고 RUNS_ROOT 바로 아래 폴더만 돌려준다 (다른 경로 접근 차단)."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"잘못된 run_id 형식: {run_id!r}")
    path = (RUNS_ROOT / run_id).resolve()
    if path.parent != RUNS_ROOT.resolve() or not path.is_dir():
        raise ValueError(f"run_id를 찾을 수 없음: {run_id}")
    return path


def write_event(record: dict) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), **record}, ensure_ascii=False) + "\n")


def _traced(tool: str, args: dict, session_id: str | None, fn: Callable[[], dict]) -> dict:
    """도구 실행 앞뒤로 기록을 남긴다. Dify가 log_event를 부르지 않아도 호출 이력이 남는다."""
    call_id = uuid.uuid4().hex[:8]
    base = {"session_id": session_id, "call_id": call_id, "tool": tool}
    write_event({**base, "event": "tool_start", "args": args})
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as e:
        write_event({**base, "event": "tool_error", "error": f"{type(e).__name__}: {e}",
                     "duration_sec": round(time.perf_counter() - t0, 3)})
        raise
    write_event({**base, "event": "tool_end", "run_id": result.get("run_id"),
                 "duration_sec": round(time.perf_counter() - t0, 3)})
    return result


@mcp.tool()
def analyze_data(dataset: str = "can_mh", grid: int = 3, session_id: str | None = None) -> dict[str, Any]:
    """시범 데이터셋을 분석해 작업 조건(물체 초기 위치 grid x grid 칸)별 시범 수·평균 길이·총 프레임을 요약한다.

    dataset: 데이터셋 이름. "can_mh"(robomimic Can: 캔 옮기기, Multi-Human 300개) 또는
             "square_mh"(robomimic Square: 너트를 기둥에 끼우기, Multi-Human 300개, 더 어려움).
    grid: 조건 격자 크기 (2~5, 기본 3).
    session_id: 같은 대화의 호출을 묶는 ID (선택). Dify에서는 대화 ID를 넣는다.
    반환: run_id(다음 도구 select_demos에 넘긴다), 조건별 통계, 품질 신호 이름. 시범 목록과 숙련도 라벨은 포함하지 않는다.
    """
    _check_session(session_id)
    if dataset not in DATASETS:
        raise ValueError(f"알 수 없는 dataset: {dataset!r}. 사용 가능: {sorted(DATASETS)}")
    if not 2 <= grid <= 5:
        raise ValueError("grid는 2~5 사이여야 한다")

    def work() -> dict:
        out = A.run(DATASETS[dataset], out_root=RUNS_ROOT, grid=grid, run_id=_new_run_id("analyze"))
        return json.loads((out / "analysis_summary.json").read_text(encoding="utf-8"))

    return _traced("analyze_data", {"dataset": dataset, "grid": grid}, session_id, work)


@mcp.tool()
def select_demos(analysis_run_id: str, budget: int = S.DEFAULT_BUDGET, seed: int = 0,
                 session_id: str | None = None) -> dict[str, Any]:
    """analyze_data 결과를 바탕으로 학습에 쓸 시범을 예산만큼 고르고, 비교용 무작위 기준선을 함께 만든다.

    analysis_run_id: analyze_data가 돌려준 run_id.
    budget: 고를 시범 수 (10~270, 기본 150). 후보는 train 분할 270개다.
    seed: 무작위 기준선의 난수 시작값.
    session_id: 같은 대화의 호출을 묶는 ID (선택).
    반환: run_id, 조건별 배분(planned/selected/shortage), 묶음별 시범 수·총 프레임, 규칙 검사 결과(checks.verdict가 pass인지 확인),
    학습용 필터 키 이름. 시범 ID 목록과 숙련도 라벨은 포함하지 않는다.
    """
    _check_session(session_id)
    if not 10 <= budget <= 270:
        raise ValueError("budget은 10~270 사이여야 한다")
    analysis_path = _run_dir(analysis_run_id) / "analysis.json"
    if not analysis_path.exists():
        raise ValueError(f"{analysis_run_id}는 analyze_data 결과가 아니다")

    def work() -> dict:
        out = S.run(analysis_path, out_root=RUNS_ROOT, budget=budget, seed=seed, run_id=_new_run_id("select"))
        return json.loads((out / "selection_summary.json").read_text(encoding="utf-8"))

    args = {"analysis_run_id": analysis_run_id, "budget": budget, "seed": seed}
    return _traced("select_demos", args, session_id, work)


def _unreviewed_select(session_id: str) -> str | None:
    """이 대화에서 select_demos가 만든 run_id 중 아직 검수하지 않은 가장 최근 것."""
    if not EVENTS_PATH.exists():
        return None
    made, reviewed = [], set()
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("session_id") != session_id:
            continue
        if e.get("tool") == "select_demos" and e.get("event") == "tool_end" and e.get("run_id"):
            made.append(e["run_id"])
        elif e.get("event") == "review":
            reviewed.add(e.get("reviewed_run_id"))
    pending = [r for r in made if r not in reviewed]
    return pending[-1] if pending else None


@mcp.tool()
def review_selection(session_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    """select_demos 결과를 저장된 파일로 다시 검사한다 (검수자). 에이전트가 보고한 내용은 보지 않는다.

    session_id: 대화 ID. 이 대화에서 아직 검수하지 않은 가장 최근 선별 결과를 검사한다.
    run_id: 특정 선별 결과를 지정할 때 (선택).
    반환: verdict(pass / revise / none), issues, warnings, 선택 수·총 프레임, 비교 묶음, 학습 계획(예상 시간).
    이번 대화에서 선별한 결과가 없으면 verdict가 none이다.
    """
    _check_session(session_id)
    if run_id is None and session_id is None:
        raise ValueError("session_id나 run_id 중 하나는 필요하다")

    def work() -> dict:
        target = run_id or _unreviewed_select(session_id)
        if target is None:
            return {"verdict": "none", "run_id": None, "detail": "이번 대화에서 검수할 선별 결과가 없음"}
        run_dir = _run_dir(target)
        if not (run_dir / "selection.json").exists():
            raise ValueError(f"{target}는 select_demos 결과가 아니다")
        result = R.review(run_dir, RUNS_ROOT)
        write_event({"session_id": session_id, "tool": "review_selection", "event": "review",
                     "reviewed_run_id": target, "verdict": result["verdict"],
                     "issues": [i["check"] for i in result["issues"]]})
        return result

    return _traced("review_selection", {"run_id": run_id}, session_id, work)


def _latest_in_session(session_id: str, event: str, key: str, verdict: str | None = None) -> str | None:
    if not EVENTS_PATH.exists():
        return None
    found = None
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("session_id") == session_id and e.get("event") == event and (verdict is None or e.get("verdict") == verdict):
            found = e.get(key) or found
    return found


@mcp.tool()
def train_evaluate(stage: str, run_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    """학습·평가 단계. 학습 자체는 코랩에서 돌고, 이 도구는 계획을 만들거나 결과를 모은다.

    stage: "prepare" = 사람이 승인한 선별 결과로 학습 계획(묶음 5개, 같은 설정)을 만든다.
           "collect" = 코랩 학습 결과를 읽어 묶음별 성공률 비교표와 1주차 성공 기준 판정을 돌려준다.
    run_id: 선별 결과의 run_id (선택). 없으면 이 대화의 최근 결과를 쓴다
            (prepare는 검수 pass를 받은 최근 선별, collect는 최근에 준비한 계획).
    session_id: 대화 ID.
    학습 설정(알고리즘, epoch, 롤아웃 횟수)은 파일럿으로 정한 값으로 고정되어 있어 바꿀 수 없다.
    """
    _check_session(session_id)
    if stage not in ("prepare", "collect"):
        raise ValueError('stage는 "prepare" 또는 "collect"')

    def work() -> dict:
        target = run_id or None  # Dify에서 빈 값으로 고정해 보내면 이 대화의 최근 결과를 쓴다
        if target is None and session_id:
            target = (_latest_in_session(session_id, "review", "reviewed_run_id", "pass") if stage == "prepare"
                      else _latest_in_session(session_id, "prepared", "run_id"))
        if target is None:
            return {"status": "no_target", "detail": "이 대화에서 대상 선별 결과(또는 학습 계획)를 찾지 못함"}
        run_dir = _run_dir(target)
        if stage == "prepare":
            out = T.prepare(run_dir, RUNS_ROOT)
            write_event({"session_id": session_id, "tool": "train_evaluate", "event": "prepared",
                         "run_id": target, "fingerprint": out["fingerprint"]})
            return out
        return T.collect(run_dir)

    return _traced(f"train_evaluate.{stage}", {"run_id": run_id}, session_id, work)


@mcp.tool()
def log_event(stage: str, event: str, detail: str = "", run_id: str | None = None,
              session_id: str | None = None) -> dict[str, Any]:
    """에이전트 실행 기록을 남긴다 (예: 검수 결과, 사람 승인/거부, 최종 보고).

    stage: 단계 이름 (예: "review", "approval", "report").
    event: 무슨 일이 있었는지 짧게 (예: "pass", "approved", "rejected").
    detail: 설명 (2000자 이내).
    run_id: 관련 실행 ID (선택). session_id: 같은 대화의 호출을 묶는 ID (선택).
    """
    _check_session(session_id)
    if run_id is not None:
        _run_dir(run_id)
    if len(stage) > 50 or len(event) > 100:
        raise ValueError("stage는 50자, event는 100자 이내")
    write_event({"session_id": session_id, "tool": "log_event", "event": "agent_log", "stage": stage,
                 "agent_event": event, "run_id": run_id, "detail": detail[:MAX_DETAIL]})
    return {"ok": True}


if __name__ == "__main__":
    print(f"[curation-tools] http://{HOST}:{PORT}/mcp (Dify: http://host.docker.internal:{PORT}/mcp)")
    mcp.run(transport="streamable-http")
