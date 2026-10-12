# 짝지어 비교용 재평가 (Kaggle 노트북 셀 1~6-1을 실행한 뒤 exec로 실행)
# 저장된 400 epoch 모델로 평가만 다시 하면서, 캔 초기 위치 50곳 각각의 성공(1)/실패(0)를 기록한다.
# 평가 시드(EVAL_SEED + i)가 같아서 i번째 위치는 모든 묶음·시드에서 같다 → 같은 위치끼리 짝지어 비교할 수 있다.
# BC-RNN(GMM)은 행동을 고를 때 torch 난수로 샘플링한다. 이 난수도 에피소드마다 EVAL_SEED + i로 고정한다
# (같은 모델은 언제 다시 평가해도 같은 결과, 묶음끼리는 같은 난수를 써서 짝 비교가 더 정확해진다).
# 학습 직후에 이어서 평가한 기존 결과(results_seeds.json)는 이 난수를 고정하지 않아 성공 횟수가 조금 다를 수 있다.
# 결과는 모델 하나 끝날 때마다 파일에 저장한다.
import json, os, time
import numpy as np
import torch

OUTP = '/kaggle/working/results_paired.json'
SETS_P = ['curated_150', 'random_150', 'train']
SEEDS_P = [1, 2, 3]
N_P, EP_P, HOR_P = 50, 400, PLAN['config']['rollout_horizon']
doc_p = json.load(open(OUTP)) if os.path.exists(OUTP) else {}
if doc_p.get('policy_seed') != 'EVAL_SEED+i':   # 난수 고정 전 결과는 버리고 새로 시작
    doc_p = {'fingerprint': PLAN['fp'], 'run_id': PLAN['run_id'], 'mode': 'paired', 'eval_seed': EVAL_SEED,
             'policy_seed': 'EVAL_SEED+i', 'epoch': EP_P, 'rollouts': N_P, 'horizon': HOR_P, 'runs': {}}


def evaluate_each(ckpt, n, horizon):
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


for seed in SEEDS_P:
    for name in SETS_P:
        key = f'{name}|seed{seed}'
        if key in doc_p['runs']:
            continue
        ck = find_ckpt(name, seed, EP_P)
        if ck is None:
            print('NO CKPT', key, flush=True)
            continue
        t0 = time.time()
        o = evaluate_each(ck, N_P, HOR_P)
        doc_p['runs'][key] = {'set': name, 'seed': seed, 'outcomes': o, 'success': sum(o), 'eval_sec': round(time.time() - t0)}
        with open(OUTP + '.tmp', 'w') as f:
            json.dump(doc_p, f)
        os.replace(OUTP + '.tmp', OUTP)
        print('PAIRED', key, sum(o), ''.join(map(str, o)), flush=True)
print('[결과] 짝 평가 완료', len(doc_p['runs']), '개 →', OUTP)
