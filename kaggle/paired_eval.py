# 짝지어 비교용 재평가 (Kaggle 노트북 셀 1~6-1을 실행한 뒤 exec로 실행)
# 저장된 400 epoch 모델로 평가만 다시 하면서, 캔 초기 위치 각각의 성공(1)/실패(0)를 기록한다.
# 평가 시드(EVAL_SEED + i)가 같아서 i번째 위치는 모든 묶음·시드에서 같다 → 같은 위치끼리 짝지어 비교할 수 있다.
# BC-RNN(GMM)은 행동을 고를 때 torch 난수로 샘플링한다. 이 난수도 에피소드마다 EVAL_SEED + i로 고정한다
# (같은 모델은 언제 다시 평가해도 같은 결과, 묶음끼리는 같은 난수를 써서 짝 비교가 더 정확해진다).
# 학습 직후에 이어서 평가한 기존 결과(results_seeds.json)는 이 난수를 고정하지 않아 성공 횟수가 조금 다를 수 있다.
# 결과는 모델 하나 끝날 때마다 파일에 저장한다.
#
# 2026-10-12 확장: 1주차 최종 평가 기준(시드 3개 x 시험 100개)에 맞춰 위치를 100개로, 묶음을 5개로 늘렸다.
# 위치마다 난수를 새로 고정하므로, 이미 50개를 평가한 모델은 51~100번만 이어서 평가하면 0~99번을 한 번에 돈 것과 같다.
# 이를 확인하려고 시작 전에 기존 모델 하나의 처음 5개 위치를 다시 평가해 저장된 결과와 비교하고, 다르면 멈춘다.
import json, os, time
import numpy as np
import torch

OUTP = '/kaggle/working/results_paired.json'
SETS_P = ['curated_150', 'random_150', 'train', 'stratified_random_150', 'random_frames']
SEEDS_P = [1, 2, 3]
N_P, EP_P, HOR_P = 100, 400, PLAN['config']['rollout_horizon']
doc_p = json.load(open(OUTP)) if os.path.exists(OUTP) else {}
if doc_p.get('policy_seed') != 'EVAL_SEED+i':   # 난수 고정 전 결과는 버리고 새로 시작
    doc_p = {'fingerprint': PLAN['fp'], 'run_id': PLAN['run_id'], 'mode': 'paired', 'eval_seed': EVAL_SEED,
             'policy_seed': 'EVAL_SEED+i', 'epoch': EP_P, 'rollouts': N_P, 'horizon': HOR_P, 'runs': {}}
doc_p['rollouts'] = N_P


def evaluate_each(ckpt, positions, horizon):
    policy, ckpt_dict = FileUtils.policy_from_checkpoint(ckpt_path=ckpt, device=DEV, verbose=False)
    env, _ = FileUtils.env_from_checkpoint(ckpt_dict=ckpt_dict, render=False, render_offscreen=False, verbose=False)
    out = []
    for i in positions:
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


def save_p():
    with open(OUTP + '.tmp', 'w') as f:
        json.dump(doc_p, f)
    os.replace(OUTP + '.tmp', OUTP)


# 이어 붙이기 전 재현성 확인: 저장된 결과가 있는 첫 모델의 처음 5개 위치를 다시 평가
if doc_p['runs'] and 'resume_check' not in doc_p:
    key0 = next(iter(doc_p['runs']))
    r0 = doc_p['runs'][key0]
    again = evaluate_each(find_ckpt(r0['set'], r0['seed'], EP_P), range(5), HOR_P)
    doc_p['resume_check'] = {'run': key0, 'stored': r0['outcomes'][:5], 'again': again, 'same': again == r0['outcomes'][:5]}
    print('[확인] 재평가 일치', doc_p['resume_check'], flush=True)
    if not doc_p['resume_check']['same']:
        raise RuntimeError('처음 5개 위치 재평가가 저장된 결과와 다르다. 이어 붙이면 안 된다')
    save_p()

for seed in SEEDS_P:
    for name in SETS_P:
        key = f'{name}|seed{seed}'
        have = (doc_p['runs'].get(key) or {}).get('outcomes', [])
        if len(have) >= N_P:
            continue
        ck = find_ckpt(name, seed, EP_P)
        if ck is None:
            # Kaggle에서 시드 1은 핵심 3묶음만 다시 학습해서, 나머지 2묶음의 시드 1 모델이 없을 수 있다.
            # 같은 계획·시드로 학습만 다시 한다 (학습이 결정적이라 코랩 시드 1과 같은 모델, 2026-10-12 확인). 평가는 1회씩만
            print('NO CKPT → 학습', key, flush=True)
            cfg = PLAN['config']
            run_set(name, dict(cfg, seed=seed), {cfg['early_eval_epoch']: 1, cfg['num_epochs']: 1})
            ck = find_ckpt(name, seed, EP_P)
            if ck is None:
                print('NO CKPT 학습 후에도 없음', key, flush=True)
                continue
        t0 = time.time()
        o = have + evaluate_each(ck, range(len(have), N_P), HOR_P)
        prev = doc_p['runs'].get(key, {})
        doc_p['runs'][key] = {'set': name, 'seed': seed, 'outcomes': o, 'success': sum(o),
                              'eval_sec': prev.get('eval_sec', 0) + round(time.time() - t0)}
        save_p()
        print('PAIRED', key, sum(o), ''.join(map(str, o)), flush=True)
print('[결과] 짝 평가 완료', len(doc_p['runs']), '개 →', OUTP)
