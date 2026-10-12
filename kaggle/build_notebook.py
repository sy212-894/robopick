"""kaggle/02_seeds.ipynb 생성: 시드 1과 같은 학습 계획을 시드 2, 3으로 다시 학습·평가한다 (Kaggle GPU)."""
import json
import sys
import textwrap
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


# 코랩 학습·평가 함수를 그대로 쓰고 경로만 바꾼다 (평가 시드 12345도 같게 → 시드 1 결과와 같은 50개 초기 상태)
fn = src["c6"].replace("/content/runs/", f"{{WORK}}/runs/").replace("/content/logs", "{WORK}/logs")
fn = fn.replace('f"{WORK}/runs/', 'f"{WORK}/runs/').replace("'{WORK}/logs'", "f'{WORK}/logs'").replace('f"{WORK}/logs/', 'f"{WORK}/logs/')
fn = fn.replace("out_dir = f\"{WORK}/runs/{set_name}_{cfg['algo']}\"", "out_dir = f\"{WORK}/runs/{set_name}_{cfg['algo']}_s{cfg['seed']}\"")
assert "/content" not in fn, fn

cells = [
    md("intro", """
# 5단계 추가 실험: 시드 2, 3 (Kaggle)

- 시드 1(코랩)과 **같은 학습 계획**(지문 c15466d53a01cedb)을 학습 시드만 바꿔 다시 학습·평가한다
- 평가 시드 12345도 같아서 모든 묶음·시드가 같은 50개 초기 상태에서 평가받는다
- 순서: (선별, 무작위, 전체) × 시드 2, 3 → (프레임 맞춘 무작위, 조건별 균등) × 시드 2, 3. 중간에 끊겨도 핵심 비교가 먼저 남는다
- 결과는 한 번 끝날 때마다 `/kaggle/working/results_seeds.json`에 바로 쓴다 (Output 탭에서 받는다)
- 체크포인트: 학습이 끝난 모델은 평가 전에 `/kaggle/working/ckpt`에 저장. 꺼지면 그 버전 Output을 입력으로 붙이고 다시 실행하면 끝난 것은 건너뛴다 (셀 6-1 설명)
- SMOKE = True면 아주 짧게(2 epoch, 롤아웃 2회) 한 번만 돌려 설치·렌더링·경로를 확인한다
- 본 실행은 Save Version → Save & Run All (브라우저를 닫아도 서버에서 끝까지 돈다)
"""),
    code("k1", src["c1"]),
    code("k2", src["c2"].replace("(10/11 코랩에서 확인한 문제 3가지를 반영)", "(코랩 노트북과 같은 고정 버전, 작업 폴더만 /kaggle/temp)")
         .replace("%cd /content", "WORK = '/kaggle/temp'\n%cd {WORK}")),
    code("k3", src["c3"].replace("os.makedirs('/content/data', exist_ok=True)", "os.makedirs(f'{WORK}/data', exist_ok=True)")
         .replace("DATA = '/content/data/can_mh_low_dim.hdf5'", "DATA = f'{WORK}/data/can_mh_low_dim.hdf5'")),
    code("k4", f"""
# 4. 학습 계획 (시드 1과 같은 plan_b64) + 실행 목록
SMOKE = False   # True: 설치·렌더링 확인용 짧은 실행
PLAN_B64 = '{plan_b64}'
import json, base64, zlib
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
SEEDS = [2, 3]
CORE = ['curated_150', 'random_150', 'train']
EXTRA = ['random_frames', 'stratified_random_150']
JOBS = [(n, s) for group in (CORE, EXTRA) for s in SEEDS for n in group]
if SMOKE:
    JOBS = [('curated_150', 2)]
print('[결과] 지문', PLAN['fp'], '| 시드 1 설정', PLAN['config'])
print('[결과] 실행 목록', len(JOBS), JOBS)
"""),
    code("k5", src["c5"].replace("PDATA = '/content/data/plan.hdf5'", "PDATA = f'{WORK}/data/plan.hdf5'")),
    code("k6", fn),
    code("k6b", """
# 6-1. 체크포인트: 노트북이 중간에 꺼져도 이어서 돌릴 수 있게 한다
#  - 결과: (묶음, 시드) 하나 끝날 때마다 results_seeds.json에 저장 → 다시 돌리면 끝난 것은 건너뜀
#  - 모델: 학습이 끝나면 평가 전에 200·400 epoch 모델을 /kaggle/working/ckpt에 복사
#          → 평가 도중 꺼지면 다시 학습하지 않고 저장된 모델로 평가만 한다
#  - 학습 도중 꺼진 실행은 처음부터 다시 학습한다. 중간 epoch에서 이어 학습하면 데이터 섞는 순서(난수 상태)가
#    달라져 '같은 시드'라는 조건이 깨지기 때문 (손해는 최대 학습 1번, 약 10분)
#  - 이어서 돌리는 법: 꺼진 버전의 Output을 노트북 입력(Add Input → Your Work)으로 붙이고 다시 Save & Run All
CKPT = '/kaggle/working/ckpt'

def find_ckpt(set_name, seed, ep):
    # 이번 세션(/kaggle/working) 또는 입력으로 붙인 이전 버전(/kaggle/input) 에서 찾는다
    pats = [f'{CKPT}/{set_name}_s{seed}/model_epoch_{ep}.pth', f'/kaggle/input/**/ckpt/{set_name}_s{seed}/model_epoch_{ep}.pth']
    for p in pats:
        hit = sorted(glob.glob(p, recursive=True))
        if hit:
            return hit[-1]
    return None

def run_set(set_name, cfg, eval_n):
    eval_epochs = sorted(eval_n)
    seed = cfg['seed']
    ckpts = {ep: find_ckpt(set_name, seed, ep) for ep in eval_epochs}
    train_sec = 0.0
    if not all(ckpts.values()):
        out_dir = f"{WORK}/runs/{set_name}_{cfg['algo']}_s{seed}"
        shutil.rmtree(out_dir, ignore_errors=True)
        save_every = eval_epochs[0] if len(eval_epochs) > 1 else cfg['num_epochs']
        t0 = time.time()
        os.makedirs(f'{WORK}/logs', exist_ok=True)
        with open(f"{WORK}/logs/{set_name}_s{seed}.log", 'w') as lf, contextlib.redirect_stdout(lf), contextlib.redirect_stderr(lf):
            train(make_config(cfg, set_name, out_dir, save_every), device=DEV)
        train_sec = time.time() - t0
        dst = f'{CKPT}/{set_name}_s{seed}'
        os.makedirs(dst, exist_ok=True)
        for ep in eval_epochs:
            src = sorted(glob.glob(f'{out_dir}/**/models/model_epoch_{ep}.pth', recursive=True))[-1]
            shutil.copy(src, f'{dst}/model_epoch_{ep}.pth')
            ckpts[ep] = f'{dst}/model_epoch_{ep}.pth'
        json.dump({'train_sec': round(train_sec)}, open(f'{dst}/train.json', 'w'))
    else:
        meta = glob.glob(f'{CKPT}/{set_name}_s{seed}/train.json') + glob.glob(f'/kaggle/input/**/ckpt/{set_name}_s{seed}/train.json', recursive=True)
        train_sec = json.load(open(meta[0]))['train_sec'] if meta else 0
        print('[체크포인트] 저장된 모델로 평가만', set_name, seed, flush=True)
    rows = {}
    for ep in eval_epochs:
        t1 = time.time()
        rows[ep] = {'success': evaluate(ckpts[ep], eval_n[ep], cfg['rollout_horizon']), 'rollouts': eval_n[ep], 'eval_sec': round(time.time() - t1)}
    return train_sec, rows
print('[결과] 체크포인트 폴더', CKPT)
"""),
    code("k7", """
# 7. 실행: (묶음, 시드) 하나 끝날 때마다 결과 파일에 바로 쓴다
import datetime, os
OUT = '/kaggle/working/results_smoke.json' if SMOKE else '/kaggle/working/results_seeds.json'
gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'
doc = json.load(open(OUT)) if os.path.exists(OUT) else {
    'fingerprint': PLAN['fp'], 'run_id': PLAN['run_id'], 'mode': 'smoke' if SMOKE else 'seeds',
    'platform': 'kaggle', 'gpu': gpu, 'eval_seed': EVAL_SEED, 'config': PLAN['config'], 'runs': {}}
# 이전 버전 결과를 입력으로 붙였으면 끝난 실행을 이어받는다
for prev in glob.glob('/kaggle/input/**/' + os.path.basename(OUT), recursive=True):
    old = json.load(open(prev))
    if old.get('fingerprint') == PLAN['fp']:
        for k, v in old['runs'].items():
            doc['runs'].setdefault(k, v)
        print('[체크포인트] 이전 결과 이어받음', prev, len(old['runs']), '개')
for name, seed in JOBS:
    key = f'{name}|seed{seed}'
    if key in doc['runs']:
        continue
    cfg = dict(PLAN['config'], seed=seed)
    if SMOKE:
        cfg.update(num_epochs=2, early_eval_epoch=1)
        eval_n = {1: 1, 2: 2}
    else:
        eval_n = {cfg['num_epochs']: cfg['rollout_n'], cfg['early_eval_epoch']: cfg['early_eval_n']}
    train_sec, rows = run_set(name, cfg, eval_n)
    fin = rows[cfg['num_epochs']]
    doc['runs'][key] = {'set': name, 'seed': seed, 'success': fin['success'], 'rollouts': fin['rollouts'],
                        'train_sec': round(train_sec), 'eval_sec': sum(r['eval_sec'] for r in rows.values()),
                        'by_epoch': {str(k): v for k, v in rows.items()},
                        'finished_at': datetime.datetime.now().isoformat(timespec='seconds')}
    with open(OUT + '.tmp', 'w') as f:
        json.dump(doc, f)
    os.replace(OUT + '.tmp', OUT)
    print('RESULT', key, json.dumps(doc['runs'][key]), flush=True)
print('[결과] 완료', len(doc['runs']), '개 →', OUT)
"""),
    md("k8md", """
### 환경 차이 확인 (선택)
시드 1(코랩)과 같은 계획·시드를 이 환경에서 다시 돌려 결과가 같은지 본다. 셀 7을 시드 1, 핵심 3개 묶음으로 바꿔 실행하고 `results_seed1_kaggle.json`에 따로 저장한다.
2026-10-12 실행 결과: 선별 47/50, 무작위 40/50, 전체 48/50 (200 epoch 22/30, 9/30, 21/30) 으로 코랩과 완전히 같았다.
"""),
    code("k8", """
# 8. (선택) 시드 1 재실행: 필요할 때만 RUN_SEED1 = True
RUN_SEED1 = False
if RUN_SEED1:
    src = [c for c in In if c.startswith('# 7.')][-1]
    src = src.replace("'/kaggle/working/results_seeds.json'", "'/kaggle/working/results_seed1_kaggle.json'")
    src = src.replace('for name, seed in JOBS:', 'for name, seed in [(n, 1) for n in CORE]:')
    get_ipython().run_cell(src)
"""),
    md("k9md", """
### 짝지어 비교 재평가 (선택)
저장된 400 epoch 모델(5개 묶음 x 시드 1~3)로 평가만 다시 하면서 캔 위치 100곳의 성공/실패를 기록한다 → `results_paired.json`. 행동 샘플링 난수도 에피소드마다 고정한다.
2026-10-12: 1주차 최종 평가 기준(시드 3개 x 시험 100개)에 맞춰 50곳 → 100곳, 3묶음 → 5묶음으로 늘렸다. 이미 평가한 50곳은 다시 돌려도 같은 결과라(시작 전에 처음 5곳으로 확인) 51~100번만 이어서 평가한다. 시드 1 모델이 없는 묶음은 같은 계획·시드로 학습만 다시 한다.
같은 위치끼리 비교하면 위치 난이도 차이가 상쇄돼 신뢰구간이 좁아진다 (`curation_tools.train_eval.paired_diff`). 코드 원본: `kaggle/paired_eval.py`.
"""),
    code("k9", "# 9. (선택) 짝지어 비교 재평가: 필요할 때만 RUN_PAIRED = True\nRUN_PAIRED = True   # 2026-10-12 최종 평가(100곳)용으로 켬. 셀 7은 끝난 실행을 건너뛰어 학습을 다시 하지 않는다\nif RUN_PAIRED:\n"
         + textwrap.indent((repo / "kaggle/paired_eval.py").read_text(encoding="utf-8"), "    ")),
]
nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                    "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out = repo / "kaggle/02_seeds.ipynb"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", out, len(cells), "cells")

