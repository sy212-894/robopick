"""승인된 학습 계획을 Kaggle에서 실행·확인·중단·재개한다 (MVP 12).

Kaggle API는 별도 환경(kaggle-cli)의 kaggle_helper.py를 하위 프로세스로 불러 쓴다. 상태는 실행 폴더의
kaggle/state.json에 남긴다.

- launch: 계획으로 노트북을 만들어 올린다. 이미 결과가 있거나, 다른 학습이 돌고 있거나, 남은 GPU가 예상 시간보다
  적으면 거부한다 (승인 뒤에만 부르는 도구지만 GPU를 낭비하지 않게)
- status: 실행 상태와 진행(끝난 실행 수)을 알려 준다. 노트북은 시작할 때 세션 번호(SESSION)를, 실행 하나가 끝날
  때마다 결과(RUNJSON)를 로그에 찍는다. 끝나면 결과 파일을 받아 등록한다 (save_results → collect)
- stop: 세션 번호로 중단한다. 이 실행 폴더가 올린 노트북만 멈춘다
- resume: 끝난 실행 결과를 노트북에 넣어 다시 올린다. 노트북은 끝난 실행을 건너뛴다

설정 (환경 변수): KAGGLE_PYTHON (kaggle-cli 환경의 python), KAGGLE_OWNER (노트북 주인 이름),
KAGGLE_WEEKLY_GPU_HOURS (API가 허용량을 주지 않을 때만 씀, 기본 30), KAGGLE_LAUNCH (1이면 launch·resume이 실제로
GPU 학습을 올린다. 기본 0 = 꺼짐: 시연·개발 중 실수로 GPU를 쓰지 않게). 토큰은 kaggle 패키지가 ~/.kaggle/access_token 또는 KAGGLE_API_TOKEN에서 읽는다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

from curation_tools import train_eval as T

REPO = Path(__file__).resolve().parent.parent
HELPER = Path(__file__).resolve().parent / "kaggle_helper.py"
KAGGLE_PYTHON = os.environ.get("KAGGLE_PYTHON", "C:/miniconda3/envs/kaggle-cli/python.exe")
OWNER = os.environ.get("KAGGLE_OWNER", "qkdsy482")
WEEKLY_GPU_HOURS = float(os.environ.get("KAGGLE_WEEKLY_GPU_HOURS", "30"))
LAUNCH_ENABLED = os.environ.get("KAGGLE_LAUNCH", "0") == "1"
ACCELERATOR = "NvidiaTeslaT4"
SLUG_PREFIX = "curation-run-"
TERMINAL = ("COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCELLED")


def run_helper(cmd: str, **args) -> dict:
    p = subprocess.run([KAGGLE_PYTHON, str(HELPER), cmd, json.dumps(args, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8", timeout=180,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = [x for x in p.stdout.splitlines() if x.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"Kaggle 도우미 응답 없음: {p.stderr.strip()[-300:]}")
    out = json.loads(lines[-1])
    if not out.pop("ok", False):
        raise RuntimeError(f"Kaggle API 오류: {out.get('error')}")
    return out


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _status_name(s: str | None) -> str:
    return (s or "").split(".")[-1].upper()


def slug_for(plan: dict) -> str:
    return f"{OWNER}/{SLUG_PREFIX}{plan['fingerprint']}"


def _state_path(run_dir: Path) -> Path:
    return run_dir / "kaggle" / "state.json"


def load_state(run_dir: Path) -> dict | None:
    p = _state_path(run_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _save_state(run_dir: Path, st: dict) -> dict:
    p = _state_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return st


def default_jobs(plan: dict) -> list[tuple[str, int]]:
    return [(name, plan["config"].get("seed", 1)) for name in plan["order"]]


def eval_n(plan: dict) -> dict[int, int]:
    c = plan["config"]
    return {c["early_eval_epoch"]: c["early_eval_n"], c["num_epochs"]: c["rollout_n"]}


# ---------- 노트북 ----------

SESSION_CELL = """
# 0. 세션 번호를 로그에 남긴다 (밖에서 중단할 때 쓴다). 컨테이너 이름 kaggle_<...>-<세션 번호>-webtier
import os, re
m = re.search(r'-(\\d{6,})-', os.environ.get('KAGGLE_CONTAINER_NAME', ''))
print('SESSION', m.group(1) if m else 'unknown', flush=True)
"""


def build_notebook(plan: dict, jobs: list[tuple[str, int]], done: dict | None = None) -> dict:
    """Square 노트북(03_square.ipynb)의 설치·데이터·학습·평가 셀을 그대로 쓰고 계획·실행 목록 셀만 만든다.
    done: 이전 실행에서 끝난 결과 {키: run}. 결과 파일에 미리 넣어 두면 실행 셀이 그 실행을 건너뛴다."""
    base = json.loads((REPO / "kaggle/03_square.ipynb").read_text(encoding="utf-8"))
    cells = {c["id"]: c for c in base["cells"]}

    def code(cid: str, text: str) -> dict:
        return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
                "source": text.strip("\n").splitlines(keepends=True)}

    ev = eval_n(plan)
    s3 = code("s3", f"""
# 3. 학습 계획 + 실행 목록 (도구 train_evaluate launch가 만든 셀)
MODE = 'main'
PLAN_B64 = '{T.compact_plan(plan)}'
import json, base64, zlib, os
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = '/kaggle/working/run'
CKPT = f'{{OUTDIR}}/ckpt_{{PLAN["fp"]}}'
os.makedirs(CKPT, exist_ok=True)
JOBS = {[tuple(j) for j in jobs]!r}
EVAL_N = {ev!r}
print('[결과] 지문', PLAN['fp'], '| 실행', len(JOBS), JOBS, flush=True)
""")
    restore = code("s6b", f"""
# 6-1. 이전 실행에서 끝난 결과 (이어서 학습할 때만 채워진다). 실행 셀이 이 키들을 건너뛴다
DONE = json.loads({json.dumps(json.dumps(done or {}, ensure_ascii=False))})
OUT = f"{{OUTDIR}}/results_{{MODE}}_{{PLAN['fp']}}.json"
if DONE and not os.path.exists(OUT):
    json.dump({{'fingerprint': PLAN['fp'], 'run_id': PLAN['run_id'], 'dataset': PLAN['dataset'], 'mode': MODE,
               'platform': 'kaggle', 'gpu': 'resumed', 'eval_seed': EVAL_SEED, 'policy_seed': 'EVAL_SEED+i',
               'time_zone': 'KST', 'config': PLAN['config'], 'eval_n': {{str(k): v for k, v in EVAL_N.items()}},
               'runs': DONE}}, open(OUT, 'w'))
print('[결과] 이어서 학습할 끝난 실행', len(DONE), flush=True)
""")
    s7 = dict(cells["s7"])
    src = "".join(s7["source"])
    marker = "    print('RESULT', key,"
    assert marker in src, "실행 셀 형식이 바뀌었다"
    src = src.replace(marker, "    print('RUNJSON', json.dumps({key: doc['runs'][key]}), flush=True)\n" + marker)
    s7["source"] = src.splitlines(keepends=True)
    order = [code("s0", SESSION_CELL), cells["s1"], cells["s2"], s3, cells["s4"], cells["s5"], cells["s6"], restore, s7]
    return {"cells": order, "metadata": base["metadata"], "nbformat": 4, "nbformat_minor": 5}


def _write_push_folder(run_dir: Path, plan: dict, nb: dict) -> Path:
    folder = run_dir / "kaggle" / "push"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.ipynb").write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    slug = slug_for(plan)
    meta = {"id": slug, "title": slug.split("/")[1], "code_file": "run.ipynb", "language": "python",
            "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_internet": True,
            "dataset_sources": [], "competition_sources": [], "kernel_sources": []}
    (folder / "kernel-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# ---------- 로그 해석 ----------

def parse_logs(lines: list[str]) -> dict:
    session, runs = None, {}
    for ln in lines:
        if ln.startswith("SESSION "):
            v = ln.split()[1]
            session = int(v) if v.isdigit() else session
        elif ln.startswith("RUNJSON "):
            try:
                runs.update(json.loads(ln[len("RUNJSON "):]))
            except json.JSONDecodeError:
                pass
    return {"session_id": session, "runs": runs}


# ---------- 단계 ----------

def gpu_left_hours() -> dict:
    q = run_helper("quota")
    allowed = q.get("gpu_allowed_hours") or WEEKLY_GPU_HOURS
    return {"used": q["gpu_used_hours"], "allowed": allowed, "left": round(allowed - q["gpu_used_hours"], 2),
            "refresh": q.get("refresh")}


def active_elsewhere(runs_root: Path, run_dir: Path) -> list[str]:
    """다른 실행 폴더에서 아직 끝나지 않은 학습 (기록상). Kaggle GPU 동시 실행을 1개로 제한한다."""
    out = []
    for p in runs_root.glob("*/kaggle/state.json"):
        if p.parent.parent == run_dir:
            continue
        st = json.loads(p.read_text(encoding="utf-8"))
        if st.get("status") not in ("complete", "error", "stopped"):
            out.append(st["slug"])
    return out


def _disabled() -> dict:
    return {"status": "disabled", "detail": "Kaggle 자동 학습이 꺼져 있다 (도구 서버를 KAGGLE_LAUNCH=1로 켜야 GPU 학습을 올린다)"}


def launch(run_dir: Path, runs_root: Path) -> dict:
    plan_path = run_dir / "plan" / "plan.json"
    if not plan_path.exists():
        raise ValueError("학습 계획이 없다. 먼저 prepare")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if T.collect(run_dir).get("status") != "not_trained":
        return {"status": "already_trained", "detail": "같은 계획의 학습 결과가 이미 있어 다시 학습하지 않는다 (collect로 조회)"}
    st = load_state(run_dir)
    if st and st.get("status") not in ("complete", "error", "stopped"):
        return {"status": "already_running", "detail": "이 계획은 이미 Kaggle에서 실행 중", "slug": st["slug"]}
    others = active_elsewhere(runs_root, run_dir)
    if others:
        return {"status": "busy", "detail": f"다른 학습이 실행 중이라 시작하지 않는다: {others}"}
    if not LAUNCH_ENABLED:
        return _disabled()
    jobs = default_jobs(plan)
    est_min = len(jobs) * T.MINUTES_BY_DATASET.get(plan["dataset"]["name"], T.MINUTES_PER_SET)
    gpu = gpu_left_hours()
    if gpu["left"] * 60 < est_min:
        return {"status": "no_gpu", "detail": f"남은 GPU {gpu['left']}시간이 예상 {est_min}분보다 적다 (초기화 {gpu['refresh']})", "gpu": gpu}
    folder = _write_push_folder(run_dir, plan, build_notebook(plan, jobs))
    r = run_helper("push", folder=str(folder), accelerator=ACCELERATOR)
    if r.get("error"):
        raise RuntimeError(f"노트북을 올리지 못함: {r['error']}")
    st = {"slug": slug_for(plan), "url": r.get("url"), "version": r.get("version"), "pushed_at": _now(),
          "fingerprint": plan["fingerprint"], "jobs": [list(j) for j in jobs], "est_minutes": est_min,
          "status": "queued", "session_id": None, "done": {}, "history": []}
    _save_state(run_dir, st)
    return {"status": "launched", "slug": st["slug"], "url": st["url"], "jobs": len(jobs), "est_minutes": est_min, "gpu": gpu}


def status(run_dir: Path, runs_root: Path) -> dict:
    st = load_state(run_dir)
    if not st:
        if T.collect(run_dir).get("status") != "not_trained":
            return {"status": "already_trained", "detail": "같은 계획의 학습 결과가 이미 있다 (collect로 조회)"}
        return {"status": "not_launched", "detail": "Kaggle에 올린 학습이 없다"}
    if st["status"] in ("complete", "stopped", "error"):
        return _summary(st)
    k = run_helper("status", slug=st["slug"])
    name = _status_name(k.get("status"))
    if name in ("RUNNING", "COMPLETE") or name.startswith("CANCEL") or name == "ERROR":
        try:
            parsed = parse_logs(run_helper("logs", slug=st["slug"], seconds=6)["lines"])
            st["session_id"] = parsed["session_id"] or st.get("session_id")
            st["done"].update(parsed["runs"])
        except RuntimeError:
            pass  # 로그를 못 읽어도 상태는 낸다
    st["kaggle_status"] = name
    if name == "RUNNING":
        st["status"] = "running"
    elif name == "COMPLETE":
        st["status"] = _ingest(run_dir, runs_root, st)
    elif name.startswith("CANCEL"):
        st["status"] = "stopped"
    elif name == "ERROR":
        st["status"] = "error"
        st["failure"] = k.get("failure")
    else:
        st["status"] = "queued"
    st["checked_at"] = _now()
    _save_state(run_dir, st)
    return _summary(st)


def _ingest(run_dir: Path, runs_root: Path, st: dict) -> str:
    dest = run_dir / "kaggle" / "out"
    dest.mkdir(parents=True, exist_ok=True)
    run_helper("output", slug=st["slug"], dest=str(dest), pattern=r"results_main_.*\.json")
    hits = sorted(dest.rglob(f"results_main_{st['fingerprint']}.json"))
    if not hits:
        st["failure"] = "결과 파일을 받지 못함"
        return "error"
    T.save_results(hits[-1], runs_root)
    return "complete"


def _summary(st: dict) -> dict:
    total = len(st.get("jobs", []))
    done = len(st.get("done", {}))
    started = dt.datetime.fromisoformat(st["pushed_at"])
    return {"status": st["status"], "slug": st["slug"], "url": st.get("url"), "done_runs": done, "total_runs": total,
            "elapsed_minutes": round((dt.datetime.now() - started).total_seconds() / 60),
            "est_minutes": st.get("est_minutes"), "kaggle_status": st.get("kaggle_status"),
            "failure": st.get("failure"), "can_stop": st["status"] in ("queued", "running") and bool(st.get("session_id")),
            "can_resume": st["status"] in ("stopped", "error") and done < total}


def stop(run_dir: Path, runs_root: Path) -> dict:
    st = load_state(run_dir)
    if not st or st["status"] not in ("queued", "running"):
        return {"status": "not_running", "detail": "중단할 학습이 없다"}
    if not st.get("session_id"):
        status(run_dir, runs_root)  # 로그에서 세션 번호를 다시 읽는다
        st = load_state(run_dir)
    if not st.get("session_id"):
        return {"status": "no_session", "detail": "세션 번호를 아직 못 읽었다 (시작 직후). 잠시 뒤 다시 시도"}
    if not st["slug"].split("/")[-1].startswith(SLUG_PREFIX):
        raise ValueError("이 도구가 올린 노트북만 멈춘다")
    r = run_helper("cancel", session_id=st["session_id"])
    if r.get("error"):
        raise RuntimeError(f"중단 실패: {r['error']}")
    st["status"] = "stopping"
    st["history"].append({"event": "stop", "at": _now(), "session_id": st["session_id"], "done": len(st["done"])})
    _save_state(run_dir, st)
    return {"status": "stopping", "done_runs": len(st["done"]), "total_runs": len(st["jobs"]),
            "detail": "끝난 실행 결과는 남고, 진행 중이던 실행은 이어서 학습할 때 처음부터 다시 한다"}


def resume(run_dir: Path, runs_root: Path) -> dict:
    st = load_state(run_dir)
    if not st or st["status"] not in ("stopped", "error"):
        return {"status": "not_stopped", "detail": "멈춘 학습이 없다"}
    others = active_elsewhere(runs_root, run_dir)
    if others:
        return {"status": "busy", "detail": f"다른 학습이 실행 중이라 시작하지 않는다: {others}"}
    if not LAUNCH_ENABLED:
        return _disabled()
    plan = json.loads((run_dir / "plan" / "plan.json").read_text(encoding="utf-8"))
    jobs = [tuple(j) for j in st["jobs"]]
    left = [j for j in jobs if f"{j[0]}|seed{j[1]}" not in st["done"]]
    est_min = len(left) * T.MINUTES_BY_DATASET.get(plan["dataset"]["name"], T.MINUTES_PER_SET)
    gpu = gpu_left_hours()
    if gpu["left"] * 60 < est_min:
        return {"status": "no_gpu", "detail": f"남은 GPU {gpu['left']}시간이 예상 {est_min}분보다 적다", "gpu": gpu}
    folder = _write_push_folder(run_dir, plan, build_notebook(plan, jobs, st["done"]))
    r = run_helper("push", folder=str(folder), accelerator=ACCELERATOR)
    if r.get("error"):
        raise RuntimeError(f"노트북을 올리지 못함: {r['error']}")
    st.update({"status": "queued", "session_id": None, "version": r.get("version"), "pushed_at": _now(),
               "est_minutes": est_min, "kaggle_status": None, "failure": None})
    st["history"].append({"event": "resume", "at": st["pushed_at"], "done": len(st["done"])})
    _save_state(run_dir, st)
    return {"status": "resumed", "left_runs": len(left), "est_minutes": est_min, "gpu": gpu}
