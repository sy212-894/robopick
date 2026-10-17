"""학습 키트: 사용자가 자기 환경(Colab, Kaggle, 리눅스 서버)에서 바로 돌릴 수 있는 학습 묶음을 만든다.

키트 = 고른 데이터 파일(필터 키 포함) + 학습 설정 파일 + 노트북 2종 + 사용법
- "선별 데이터로 학습"(train_curated.ipynb): 선별 묶음 1개만 학습 → 결과를 올리면 "결과 확인"
- "선별·무작위·전체 비교 학습"(train_compare.ipynb): 3묶음 학습(약 3배 시간) → 결과를 올리면 "선별 효과 판정"
노트북은 Square 노트북(kaggle/03_square.ipynb)의 설치·학습·평가 셀을 그대로 쓰고, 환경 판단·계획·데이터 셀만 새로 만든다.
평가는 그동안의 실험과 같다: 마지막 epoch 시험 100회(중간 epoch 30회), 시험마다 시작 위치·행동 난수를 12345+i로 고정
(그래서 우리 실험·다른 사용자 결과와 같은 위치끼리 짝지어 비교할 수 있다).
"""
from __future__ import annotations

import json
from pathlib import Path

from curation_tools import train_eval as T

REPO = Path(__file__).resolve().parent.parent
FINAL_N, EARLY_N = 100, 30  # 1주차 최종 평가 기준 (계획의 rollout_n과 상관없이 고정, 한계 보완 실험과 같음)
# 묶음 하나(학습 + 평가 130회)의 실측 시간 (분, Kaggle T4). Can: 예산 60 2차 실험(10/17) 실행당 약 35~40분.
# 다른 데이터는 재지 않았다 (None → "측정 안 됨")
KIT_MINUTES = {"can_mh": 40}
KINDS = {
    "curated": {"file": "train_curated.ipynb", "title": "선별 데이터로 학습", "after": "결과 확인 (성공률과 근거표의 비슷한 실험)"},
    "compare": {"file": "train_compare.ipynb", "title": "선별·무작위·전체 비교 학습", "after": "선별 효과 판정 (무작위보다 나은지, 전체 대비 하락 5%p 이내인지)"},
}


def default_jobs(plan: dict) -> list[tuple[str, int]]:
    return [(name, plan["config"].get("seed", 1)) for name in plan["order"]]


def kit_jobs(plan: dict, kind: str) -> list[tuple[str, int]]:
    seed = plan["config"].get("seed", 1)
    cur = next(n for n in plan["order"] if n.startswith("curated"))
    if kind == "curated":
        return [(cur, seed)]
    rnd = next(n for n in plan["order"] if n.startswith("random_") and n != "random_frames")
    return [(cur, seed), (rnd, seed), ("train", seed)]


def eval_n(plan: dict) -> dict[int, int]:
    c = plan["config"]
    return {c["early_eval_epoch"]: EARLY_N, c["num_epochs"]: FINAL_N}


def data_filename(plan: dict) -> str:
    return f"{plan['dataset']['name']}_curated.hdf5"


ENV_CELL = """
# 0. 실행 환경 판단 (Colab, Kaggle, 그 밖의 리눅스) → 결과·작업 폴더를 맞춘다. 위에서부터 실행만 하면 된다
import os, sys
if os.path.exists('/kaggle'):
    ENV, BASE, WORK = 'kaggle', '/kaggle/working', '/kaggle/temp'
elif 'google.colab' in sys.modules or os.path.exists('/content'):
    ENV, BASE, WORK = 'colab', '/content', '/content/work'
else:
    ENV = 'local'
    BASE = os.path.abspath('.')
    WORK = os.path.join(BASE, 'work')
os.makedirs(WORK, exist_ok=True)
# 화면 없는 서버용 렌더링. 화면이 있는 리눅스에서 오류가 나면 'glfw'로 바꾼다. 윈도우에서 직접 실행은 보장하지 않는다
os.environ.setdefault('MUJOCO_GL', 'egl')
print('[결과] 환경', ENV, '| 결과 폴더', BASE, '| 작업 폴더', WORK)
"""

GPU_CELL = """
# 1. GPU 확인 (없어도 돌지만 아주 느리다)
import torch
print('[결과] python', sys.version.split()[0], '| torch', torch.__version__, '| GPU', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '없음')
"""


def _code(cid: str, text: str) -> dict:
    return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def _md(cid: str, text: str) -> dict:
    return {"cell_type": "markdown", "id": cid, "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def build_notebook(plan: dict, jobs: list[tuple[str, int]], kind: str = "curated") -> dict:
    base = json.loads((REPO / "kaggle/03_square.ipynb").read_text(encoding="utf-8"))
    cells = {c["id"]: c for c in base["cells"]}
    info = KINDS[kind]
    intro = _md("intro", f"""
# 학습 키트: {info['title']}

- 데이터 `{plan['dataset']['name']}`, 학습 계획 지문 `{plan['fingerprint']}`, 학습 {len(jobs)}개: {', '.join(n for n, _ in jobs)}
- Colab, Kaggle, 리눅스 GPU 서버에서 위에서부터 차례로 실행한다. 첫 셀이 환경을 알아서 경로를 맞춘다
- 키트의 데이터 파일 `{data_filename(plan)}`을 이 노트북과 같은 폴더(Kaggle은 입력 데이터)에 두면 그 파일을 쓰고, 없으면 원본을 내려받아 같은 묶음을 만든다
- 평가: 시뮬레이터(robosuite)에서 {plan['config']['num_epochs']} epoch 모델로 시험 {FINAL_N}회({plan['config']['early_eval_epoch']} epoch {EARLY_N}회), 시험마다 시작 위치·행동 난수를 12345+i로 고정
- 끝나면 결과 폴더의 `results_main_{plan['fingerprint']}.json`을 에이전트에 올리면 {info['after']}을 받는다
- 실제 로봇 데이터는 학습은 되지만 이 노트북이 성공률을 잴 수 없다 (시뮬레이터가 필요)
""")
    s2 = ("".join(cells["s2"]["source"]).replace("WORK = '/kaggle/temp'\n", "")
          .replace("작업 폴더만 /kaggle/temp", "작업 폴더는 0번 셀이 정한 WORK"))
    assert "/kaggle/temp" not in s2, "설치 셀 형식이 바뀌었다"
    plan_cell = _code("s3", f"""
# 3. 학습 계획 + 실행 목록 (에이전트가 만든 셀)
MODE = 'main'
KIT = '{kind}'
PLAN_B64 = '{T.compact_plan(plan)}'
import json, base64, zlib
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = f'{{BASE}}/curation_results'
CKPT = f'{{OUTDIR}}/ckpt_{{PLAN["fp"]}}'
os.makedirs(CKPT, exist_ok=True)
JOBS = {[tuple(j) for j in jobs]!r}
EVAL_N = {eval_n(plan)!r}
print('[결과] 데이터', PLAN['dataset'], '| 지문', PLAN['fp'], '| 실행', len(JOBS), JOBS, '| 평가', EVAL_N)
""")
    data_cell = _code("s4", f"""
# 4. 데이터: 키트의 데이터 파일이 있으면 그대로 쓰고, 없으면 원본을 내려받아 묶음별 필터 키를 넣는다
import glob, shutil, h5py, numpy as np
DATA_FILE = '{data_filename(plan)}'
found = next((p for p in [os.path.join(BASE, DATA_FILE), os.path.abspath(DATA_FILE)] + glob.glob(f'/kaggle/input/**/{{DATA_FILE}}', recursive=True)
              if os.path.exists(p)), None)
os.makedirs(f'{{WORK}}/data', exist_ok=True)
PDATA = f'{{WORK}}/data/plan.hdf5'
if found:
    shutil.copy(found, PDATA)
elif PLAN.get('hf_path'):
    src = f"{{WORK}}/data/{{PLAN['dataset']}}.hdf5"
    if not os.path.exists(src):
        !wget -q -O {{src}} 'https://huggingface.co/datasets/robomimic/robomimic_datasets/resolve/main/{{PLAN["hf_path"]}}?download=true'
    shutil.copy(src, PDATA)
else:
    raise SystemExit(f'키트의 데이터 파일 {{DATA_FILE}}을 이 노트북과 같은 폴더에 올려 주세요 (내려받을 원본이 없는 데이터)')
with h5py.File(PDATA, 'a') as f:
    for k, ids in SETS.items():
        if f'mask/{{k}}' in f:
            del f[f'mask/{{k}}']
        f.create_dataset(f'mask/{{k}}', data=np.array(ids, dtype='S'))
    print('[결과] 데이터', found or 'Hugging Face 원본', '| 필터 키', {{k: len(f[f'mask/{{k}}']) for k in SETS}})
""")
    config_cell = _code("s6b", """
# 6-1. 실제로 쓰는 robomimic 설정을 결과 폴더에 저장 (robomimic train.py --config 로도 쓸 수 있다)
for name, seed in JOBS:
    c = make_config(dict(PLAN['config'], seed=seed), name, f'{CKPT}/{name}_s{seed}', PLAN['config']['num_epochs'])
    open(f'{OUTDIR}/robomimic_config_{name}.json', 'w').write(c.dump())
print('[결과] 설정 파일', sorted(glob.glob(f'{OUTDIR}/robomimic_config_*.json')))
""")
    s7 = "".join(cells["s7"]["source"])
    for a, b in (("'platform': 'kaggle'", "'platform': ENV, 'kit': KIT"),
                 ("print('[결과] 완료', len(doc['runs']), '개 →', OUT)",
                  "print('[결과] 완료', len(doc['runs']), '개 →', OUT)\nprint('이 결과 파일을 에이전트에 올리면 판정·결과 확인을 받는다:', OUT)")):
        assert a in s7, "실행 셀 형식이 바뀌었다"
        s7 = s7.replace(a, b)
    order = [intro, _code("s0", ENV_CELL), _code("s1", GPU_CELL), _code("s2", s2), plan_cell, data_cell,
             cells["s6"], config_cell, _code("s7", s7)]
    return {"cells": order, "metadata": base["metadata"], "nbformat": 4, "nbformat_minor": 5}


def train_settings(plan: dict) -> dict:
    """키트의 학습 설정 파일: robomimic 설정 항목 이름으로 적은 우리 학습 설정과 평가 방법."""
    c = plan["config"]
    return {
        "fingerprint": plan["fingerprint"], "dataset": plan["dataset"]["name"], "data_file": data_filename(plan),
        "filter_keys": {k: len(v) for k, v in plan["sets"].items()},
        "robomimic": {"algo_name": "bc", "algo.rnn.enabled": c["algo"] == "bc_rnn", "algo.rnn.horizon": 10,
                      "algo.rnn.hidden_dim": 400, "algo.rnn.num_layers": 2, "algo.gmm.enabled": True, "algo.actor_layer_dims": [],
                      "train.seq_length": 10, "train.num_epochs": c["num_epochs"], "experiment.epoch_every_n_steps": c["steps_per_epoch"],
                      "train.batch_size": c["batch_size"], "train.seed": c.get("seed", 1), "train.hdf5_filter_key": "<묶음 이름>",
                      "observation.modalities.obs.low_dim": ["robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos", "object"]},
        "evaluation": {"epochs": {str(k): v for k, v in eval_n(plan).items()}, "horizon": c["rollout_horizon"],
                       "seed": "시험 i마다 numpy·torch 난수 12345+i", "success": "환경의 is_success()['task']"},
        "note": "노트북이 실행될 때 robomimic 전체 설정 파일(robomimic_config_<묶음>.json)도 결과 폴더에 저장한다",
    }


README = """학습 키트 사용법

1. 노트북 하나를 고른다
   - train_curated.ipynb : 고른 데이터로 1번 학습. 결과를 올리면 성공률과 근거(비슷한 실험 결과)를 보여 준다
   - train_compare.ipynb : 고른 데이터·같은 개수 무작위·전체 데이터를 각각 학습(약 3배 시간). 결과를 올리면 선별 효과를 판정한다
2. Colab, Kaggle 또는 리눅스 GPU 서버에서 노트북을 열고, 데이터 파일({data})을 노트북과 같은 폴더에 둔다
   (Kaggle은 "Add Input"으로 올린다. 파일이 없으면 노트북이 원본을 내려받아 같은 묶음을 만든다 - 원본을 내려받을 수 있는 데이터만)
3. 위에서부터 차례로 실행한다. 첫 셀이 환경을 알아서 경로를 맞춘다
4. 끝나면 결과 폴더(curation_results)의 results_main_{fp}.json을 에이전트 웹 화면에 올린다

학습 설정: train_settings.json (robomimic 설정 항목 이름). 예상 시간: 묶음 하나에 {minutes}
주의: 윈도우에서 직접 실행은 보장하지 않는다. 실제 로봇 데이터는 학습은 되지만 노트북이 성공률을 잴 수 없다
"""


def build_kit(run_dir: Path) -> dict:
    """선별 실행 폴더(plan 포함)에 kit/ 폴더를 만들고 파일 목록을 돌려준다. 데이터 파일은 선별이 만든 복사본을 가리킨다."""
    plan = json.loads((run_dir / "plan" / "plan.json").read_text(encoding="utf-8"))
    out = run_dir / "kit"
    out.mkdir(exist_ok=True)
    files = {}
    for kind, info in KINDS.items():
        nb = build_notebook(plan, kit_jobs(plan, kind), kind)
        (out / info["file"]).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
        files[info["file"]] = {"kind": kind, "title": info["title"], "runs": len(kit_jobs(plan, kind)), "after": info["after"]}
    (out / "train_settings.json").write_text(json.dumps(train_settings(plan), ensure_ascii=False, indent=1), encoding="utf-8")
    minutes = KIT_MINUTES.get(plan["dataset"]["name"])
    (out / "README.txt").write_text(README.format(data=data_filename(plan), fp=plan["fingerprint"], minutes=f"T4 GPU 약 {minutes}분 (실측)" if minutes else "측정 안 됨"), encoding="utf-8")
    data = run_dir / data_filename(plan)
    manifest = {"run_id": plan["run_id"], "fingerprint": plan["fingerprint"], "dataset": plan["dataset"]["name"],
                "kit_files": {**files, "train_settings.json": {"title": "학습 설정"}, "README.txt": {"title": "사용법"}},
                "data_file": {"file": data.name, "exists": data.exists(), "size_mb": round(data.stat().st_size / 1e6, 1) if data.exists() else None},
                "minutes_per_run": minutes, "can_download_original": bool(plan["dataset"].get("hf_path"))}
    (out / "kit.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest
