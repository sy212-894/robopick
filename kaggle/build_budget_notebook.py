"""kaggle/04_budget.ipynb 생성: Can 예산 135개(학습 후보 270개의 50%) 실험 (2026-10-12, 1주차 "50% 이하" 기준).

Square 노트북(03_square.ipynb)의 설치·데이터·학습·평가 셀을 그대로 쓰고 계획·실행 목록 셀만 바꾼다.
- 평가: 물체 위치(np)와 행동 샘플링(torch) 난수를 에피소드마다 EVAL_SEED + i로 고정, 위치별 성공/실패 기록 → 짝지은 비교
- 실행: 선별 135·무작위 135 x 시드 1·2·3 (전체 데이터 기준선은 Can 본 실험의 train 모델과 같아서 다시 학습하지 않는다.
  짝 평가 결과는 Can 노트북의 results_paired.json(100곳)에서 가져온다)
- 평가 횟수: 200 epoch 30회, 400 epoch 100회 (1주차 최종 평가 기준 시험 100개)

사용: python kaggle/build_budget_notebook.py . C:/curation-data/runs/R-20261012-select-b135/plan/plan_b64.txt
먼저 build_square_notebook.py로 03_square.ipynb를 만들어 둬야 한다.
"""
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
plan_b64 = Path(sys.argv[2]).read_text(encoding="ascii").strip()
base = json.loads((repo / "kaggle/03_square.ipynb").read_text(encoding="utf-8"))
cells = {c["id"]: c for c in base["cells"]}


def code(cid, text):
    return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def md(cid, text):
    return {"cell_type": "markdown", "id": cid, "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


intro = md("intro", """
# B 실험: Can 예산 135개 (Kaggle)

- 1주차 성공 기준 "학습 후보의 50% 이하 시범으로 전체 대비 하락 5%p 이내"를 문장 그대로 확인한다. 본 실험(150개)은 56%였다
- 학습 계획은 로컬 `select_demos(budget=135)` → `review` → `train_evaluate(prepare)`가 만든 `plan_b64.txt` (본 실험과 같은 분석·설정, 예산만 다름)
- 실행: 선별 135 · 무작위 135 x 시드 1·2·3. 전체 데이터 기준선은 본 실험 train 모델과 같아 다시 학습하지 않는다
- 평가: 200 epoch 30회 + 400 epoch 100회. 물체 위치와 행동 샘플링 난수를 에피소드마다 고정하고 위치별 성공/실패를 기록한다 (Can 짝 평가와 같은 위치·같은 난수)
- 판정 (결과 보기 전에 정함): 짝지은 비교, 시드 3개 x 시험 100개, 세 시드 모두 같은 방향일 때만 "차이 있음"
- 결과와 체크포인트는 `/kaggle/working/budget/` (세션 설정 Persistence = Files only). 꺼지면 다시 Run All → 끝난 실행은 건너뛴다
""")
s3 = code("s3", f"""
# 3. 학습 계획 + 실행 목록
MODE = 'main'
PLAN_B64 = '{plan_b64}'
import json, base64, zlib, os
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = '/kaggle/working/budget'
CKPT = f'{{OUTDIR}}/ckpt_{{PLAN["fp"]}}'
os.makedirs(CKPT, exist_ok=True)
CORE = ['curated_135', 'random_135']
JOBS = [(n, s) for s in (1, 2, 3) for n in CORE]
EVAL_N = {{PLAN['config']['early_eval_epoch']: PLAN['config']['early_eval_n'], PLAN['config']['num_epochs']: PLAN['config']['rollout_n']}}
print('[결과] 데이터', PLAN['dataset'], '| 지문', PLAN['fp'], '| 실행', len(JOBS), JOBS)
print('[결과] 설정', PLAN['config'], '| 평가', EVAL_N)
""")
order = [intro, cells["s1"], cells["s2"], s3, cells["s4"], cells["s5"], cells["s6"], cells["s7"]]
nb = {"cells": order, "metadata": base["metadata"], "nbformat": 4, "nbformat_minor": 5}
out = repo / "kaggle/04_budget.ipynb"
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", out, len(order), "cells")
