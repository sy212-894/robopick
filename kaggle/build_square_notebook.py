"""kaggle/03_square.ipynb 생성 스크립트 (6단계 Square). Can 노트북(02_seeds.ipynb)과 별개 파일이다.

Can에서 배운 점을 처음부터 넣었다.
- 평가 시드: 물체 초기 위치(np)와 행동 샘플링(torch)을 에피소드마다 EVAL_SEED + i로 고정 → 언제 다시 평가해도 같은 결과,
  묶음끼리 같은 위치·같은 난수라 짝지어 비교 가능. 위치별 성공(1)/실패(0)를 처음부터 기록한다
- 체크포인트: 결과는 실행(묶음 x 시드)마다, 모델은 평가 전에 /kaggle/working/square 아래 저장 → 끊겨도 이어서 실행
- 모드: pilot(전체·무작위, 시드 1, 100 epoch마다 10회) / main(5개 묶음 x 시드 1~3, 200 epoch 30회 + 400 epoch 50회)

사용: python kaggle/build_square_notebook.py . C:/curation-data/runs/<square 선별 run>/plan/plan_b64.txt
"""
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
plan_b64 = Path(sys.argv[2]).read_text(encoding="ascii").strip()
colab = json.loads((repo / "colab/01_train_eval.ipynb").read_text(encoding="utf-8"))
src = {c.get("id"): "".join(c["source"]) for c in colab["cells"]}


def code(cid, text):
    return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def md(cid, text):
    return {"cell_type": "markdown", "id": cid, "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


cells = [
    md("intro", """
# 6단계: Square 학습·평가 (Kaggle)

- 데이터: robomimic Square(너트를 기둥에 끼우기) Multi-Human 300개. 학습 계획은 로컬 `train_evaluate(prepare)`가 만든 `plan_b64.txt`
- MODE = "pilot": 전체(train)·무작위 150 두 묶음, 시드 1, 100·200·300·400 epoch마다 10회 평가 → 성공률이 바닥/천장인지, 시간이 얼마나 드는지 확인
- MODE = "main": 5개 묶음 x 시드 1·2·3, 200 epoch 30회 + 400 epoch 50회 평가
- 평가: 물체 초기 위치와 행동 샘플링 난수를 에피소드마다 고정 (같은 모델은 언제 평가해도 같은 결과). 위치별 성공/실패를 기록해 짝지어 비교에 쓴다
- 결과와 체크포인트는 `/kaggle/working/square/` (세션 설정 Persistence = Files only). 꺼지면 다시 Run All → 끝난 실행은 건너뛰고, 평가 도중 끊긴 실행은 저장된 모델로 평가만 한다
"""),
    code("s1", src["c1"]),
    code("s2", src["c2"].replace("(10/11 코랩에서 확인한 문제 3가지를 반영)", "(코랩 노트북과 같은 고정 버전, 작업 폴더만 /kaggle/temp)")
         .replace("%cd /content", "WORK = '/kaggle/temp'\n%cd {WORK}")),
    code("s3", f"""
# 3. 학습 계획 + 모드
MODE = 'pilot'   # 'pilot' 또는 'main'
PLAN_B64 = '{plan_b64}'
import json, base64, zlib, os
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = '/kaggle/working/square'
CKPT = f'{{OUTDIR}}/ckpt'
os.makedirs(CKPT, exist_ok=True)
if MODE == 'pilot':
    JOBS = [('train', 1), ('random_150', 1)]
    EVAL_N = {{100: 10, 200: 10, 300: 10, 400: 10}}
else:
    CORE = ['curated_150', 'random_150', 'train']
    EXTRA = ['random_frames', 'stratified_random_150']
    JOBS = [(n, s) for group in (CORE, EXTRA) for s in (1, 2, 3) for n in group]
    EVAL_N = {{PLAN['config']['early_eval_epoch']: PLAN['config']['early_eval_n'], PLAN['config']['num_epochs']: PLAN['config']['rollout_n']}}
print('[결과] 데이터', PLAN['dataset'], '| 지문', PLAN['fp'], '| 모드', MODE, '| 실행', len(JOBS), JOBS)
print('[결과] 설정', PLAN['config'], '| 평가', EVAL_N)
"""),
    code("s4", """
# 4. 데이터 다운로드 (계획에 적힌 데이터셋)
os.environ['MUJOCO_GL'] = 'egl'   # 화면 없는 서버용 렌더링 설정
os.makedirs(f'{WORK}/data', exist_ok=True)
DATA = f"{WORK}/data/{PLAN['dataset']}.hdf5"
if not os.path.exists(DATA):
    !wget -q -O {DATA} 'https://huggingface.co/datasets/robomimic/robomimic_datasets/resolve/main/{PLAN["hf_path"]}?download=true'
!ls -la {DATA}
"""),
    code("s5", src["c5"].replace("PDATA = '/content/data/plan.hdf5'", "PDATA = f'{WORK}/data/plan.hdf5'")),
    code("s6", """
# 6. 학습·평가 함수 (평가 난수 고정, 위치별 결과 기록, 체크포인트)
import contextlib, glob, shutil, time, torch, numpy as np
from robomimic.config import config_factory
from robomimic.scripts.train import train
import robomimic.utils.file_utils as FileUtils
DEV = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
EVAL_SEED = 12345

def make_config(cfg, set_name, out_dir, save_every):
    config = config_factory(algo_name='bc')
    with config.values_unlocked():
        config.experiment.name = f"{set_name}_{cfg['algo']}"
        config.train.data = [{'path': PDATA}]
        config.train.output_dir = out_dir
        config.train.hdf5_filter_key = set_name
        config.train.num_epochs = cfg['num_epochs']
        config.experiment.epoch_every_n_steps = cfg['steps_per_epoch']
        config.train.batch_size = cfg['batch_size']
        config.train.seed = cfg['seed']
        config.train.cuda = torch.cuda.is_available()
        config.experiment.validate = False
        config.experiment.rollout.enabled = False
        config.experiment.render_video = False
        config.experiment.logging.log_tb = False
        config.experiment.save.enabled = True
        config.experiment.save.every_n_epochs = save_every
        config.experiment.save.on_best_validation = False
        config.experiment.save.on_best_rollout_return = False
        config.experiment.save.on_best_rollout_success_rate = False
        config.observation.modalities.obs.low_dim = ['robot0_eef_pos', 'robot0_eef_quat', 'robot0_gripper_qpos', 'object']
        if cfg['algo'] == 'bc_rnn':   # robomimic 논문의 low_dim BC-RNN 설정
            config.algo.rnn.enabled = True
            config.algo.rnn.horizon = 10
            config.algo.rnn.hidden_dim = 400
            config.algo.rnn.num_layers = 2
            config.train.seq_length = 10
            config.algo.gmm.enabled = True
            config.algo.actor_layer_dims = ()
    return config

def evaluate(ckpt, n, horizon):
    # i번째 에피소드: 물체 초기 위치(np)와 행동 샘플링(torch) 난수를 모두 EVAL_SEED + i로 고정
    policy, ckpt_dict = FileUtils.policy_from_checkpoint(ckpt_path=ckpt, device=DEV, verbose=False)
    env, _ = FileUtils.env_from_checkpoint(ckpt_dict=ckpt_dict, render=False, render_offscreen=False, verbose=False)
    out = []
    for i in range(n):
        np.random.seed(EVAL_SEED + i)
        torch.manual_seed(EVAL_SEED + i)
        policy.start_episode()
        obs = env.reset()
        ok = 0
        for t in range(horizon):
            obs, r, done, _ = env.step(policy(ob=obs))
            if env.is_success()['task']:
                ok = 1
                break
        out.append(ok)
    return out

def find_ckpt(set_name, seed, ep):
    hit = sorted(glob.glob(f'{CKPT}/{set_name}_s{seed}/model_epoch_{ep}.pth'))
    return hit[-1] if hit else None

def run_set(set_name, cfg, eval_n):
    eval_epochs = sorted(eval_n)
    seed = cfg['seed']
    dst = f'{CKPT}/{set_name}_s{seed}'
    ckpts = {ep: find_ckpt(set_name, seed, ep) for ep in eval_epochs}
    if all(ckpts.values()):
        train_sec = json.load(open(f'{dst}/train.json'))['train_sec'] if os.path.exists(f'{dst}/train.json') else 0
        print('[체크포인트] 저장된 모델로 평가만', set_name, seed, flush=True)
    else:
        out_dir = f"{WORK}/runs/{set_name}_s{seed}"
        shutil.rmtree(out_dir, ignore_errors=True)
        save_every = eval_epochs[1] - eval_epochs[0] if len(eval_epochs) > 1 and eval_epochs[0] * len(eval_epochs) == eval_epochs[-1] else eval_epochs[0]
        t0 = time.time()
        os.makedirs(f'{WORK}/logs', exist_ok=True)
        with open(f"{WORK}/logs/{set_name}_s{seed}.log", 'w') as lf, contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
            train(make_config(cfg, set_name, out_dir, save_every), device=DEV)
        train_sec = round(time.time() - t0)
        os.makedirs(dst, exist_ok=True)
        for ep in eval_epochs:   # 평가 전에 모델부터 저장 (평가 도중 꺼져도 다시 학습하지 않게)
            shutil.copy(sorted(glob.glob(f'{out_dir}/**/models/model_epoch_{ep}.pth', recursive=True))[-1], f'{dst}/model_epoch_{ep}.pth')
            ckpts[ep] = f'{dst}/model_epoch_{ep}.pth'
        json.dump({'train_sec': train_sec}, open(f'{dst}/train.json', 'w'))
    rows = {}
    for ep in eval_epochs:
        t1 = time.time()
        o = evaluate(ckpts[ep], eval_n[ep], cfg['rollout_horizon'])
        rows[str(ep)] = {'success': sum(o), 'rollouts': len(o), 'outcomes': o, 'eval_sec': round(time.time() - t1)}
    return train_sec, rows
print('[결과] 함수 준비, 장치', DEV)
"""),
    code("s7", """
# 7. 실행: (묶음, 시드) 하나 끝날 때마다 결과 파일에 저장, 끝난 것은 건너뜀
import datetime
KST = datetime.timezone(datetime.timedelta(hours=9))
OUT = f'{OUTDIR}/results_{MODE}.json'
gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'
doc = json.load(open(OUT)) if os.path.exists(OUT) else {
    'fingerprint': PLAN['fp'], 'run_id': PLAN['run_id'], 'dataset': PLAN['dataset'], 'mode': MODE, 'platform': 'kaggle',
    'gpu': gpu, 'eval_seed': EVAL_SEED, 'policy_seed': 'EVAL_SEED+i', 'time_zone': 'KST', 'config': PLAN['config'],
    'eval_n': {str(k): v for k, v in EVAL_N.items()}, 'runs': {}}
for name, seed in JOBS:
    key = f'{name}|seed{seed}'
    if key in doc['runs']:
        continue
    cfg = dict(PLAN['config'], seed=seed)
    train_sec, rows = run_set(name, cfg, EVAL_N)
    last = rows[str(max(EVAL_N))]
    doc['runs'][key] = {'set': name, 'seed': seed, 'success': last['success'], 'rollouts': last['rollouts'],
                        'train_sec': train_sec, 'eval_sec': sum(r['eval_sec'] for r in rows.values()), 'by_epoch': rows,
                        'finished_at': datetime.datetime.now(KST).isoformat(timespec='seconds')}
    with open(OUT + '.tmp', 'w') as f:
        json.dump(doc, f)
    os.replace(OUT + '.tmp', OUT)
    print('RESULT', key, {ep: f"{r['success']}/{r['rollouts']}" for ep, r in rows.items()}, 'train', train_sec, flush=True)
print('[결과] 완료', len(doc['runs']), '개 →', OUT)
"""),
]
nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                    "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out = repo / "kaggle/03_square.ipynb"
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", out, len(cells), "cells")
