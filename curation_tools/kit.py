"""학습 키트: 사용자가 자기 환경에서 바로 돌릴 수 있는 학습 노트북을 만든다.

Square 노트북(kaggle/03_square.ipynb)의 설치·데이터·학습·평가 셀을 그대로 쓰고, 학습 계획·실행 목록 셀만 계획으로 채운다.
평가는 그동안의 실험과 같다: 400 epoch 시험 100회(200 epoch 30회), 시작 위치·행동 난수를 시험마다 12345+i로 고정.
"""
from __future__ import annotations

import json
from pathlib import Path

from curation_tools import train_eval as T

REPO = Path(__file__).resolve().parent.parent


def default_jobs(plan: dict) -> list[tuple[str, int]]:
    return [(name, plan["config"].get("seed", 1)) for name in plan["order"]]


def eval_n(plan: dict) -> dict[int, int]:
    c = plan["config"]
    return {c["early_eval_epoch"]: c["early_eval_n"], c["num_epochs"]: c["rollout_n"]}


def build_notebook(plan: dict, jobs: list[tuple[str, int]]) -> dict:
    base = json.loads((REPO / "kaggle/03_square.ipynb").read_text(encoding="utf-8"))
    cells = {c["id"]: c for c in base["cells"]}

    def code(cid: str, text: str) -> dict:
        return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
                "source": text.strip("\n").splitlines(keepends=True)}

    s3 = code("s3", f"""
# 3. 학습 계획 + 실행 목록
MODE = 'main'
PLAN_B64 = '{T.compact_plan(plan)}'
import json, base64, zlib, os
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = '/kaggle/working/run'
CKPT = f'{{OUTDIR}}/ckpt_{{PLAN["fp"]}}'
os.makedirs(CKPT, exist_ok=True)
JOBS = {[tuple(j) for j in jobs]!r}
EVAL_N = {eval_n(plan)!r}
print('[결과] 지문', PLAN['fp'], '| 실행', len(JOBS), JOBS, flush=True)
""")
    order = [cells["s1"], cells["s2"], s3, cells["s4"], cells["s5"], cells["s6"], cells["s7"]]
    return {"cells": order, "metadata": base["metadata"], "nbformat": 4, "nbformat_minor": 5}
