# Kaggle 시드 실험 이어서 돌리기

노트북: https://www.kaggle.com/code/qkdsy482/notebook6e1087472a/edit (세션 설정: GPU T4, 인터넷 켜기, Persistence = Files only)

## 무엇이 어디에 저장되나 (세션이 꺼져도 남음, Files only)
- `/kaggle/working/results_seeds.json`: 시드 2, 3 결과. 학습 1번(묶음 1개 x 시드 1개)이 끝날 때마다 저장
- `/kaggle/working/results_seed1_kaggle.json`: Kaggle에서 다시 돌린 시드 1 결과 (환경 차이 확인용, 선별·무작위·전체)
- `/kaggle/working/ckpt/<묶음>_s<시드>/`: 학습이 끝난 모델 (200, 400 epoch). 평가 도중 꺼지면 다시 학습하지 않고 평가만 한다
- 학습 도중 꺼진 실행은 처음부터 다시 학습한다 (같은 시드 조건을 지키기 위해. 손해는 최대 학습 1번, 약 8분)

## 이어서 돌리는 법
1. 노트북 편집 화면을 연다. 오른쪽 패널 Session options에서 GPU T4, Internet on, Persistence = Files only 인지 확인
2. 셀 4의 `SMOKE = False` 확인
3. **시드 1 재실행이 필요하면**: 셀 8의 `RUN_SEED1 = True`로 바꿔 실행 (아래 한 줄과 같은 동작)
   ```python
   src = [c for c in In if c.startswith('# 7.')][-1].replace("'/kaggle/working/results_seeds.json'", "'/kaggle/working/results_seed1_kaggle.json'").replace('for name, seed in JOBS:', 'for name, seed in [(n, 1) for n in CORE]:'); get_ipython().run_cell(src)
   ```
4. **시드 2, 3**: Run All (셀 8은 `RUN_SEED1 = False`면 아무것도 하지 않는다)
5. 끝난 실행은 결과 파일에 있어서 자동으로 건너뛴다. 출력의 `RESULT ...` 줄과 `[체크포인트] 저장된 모델로 평가만` 줄로 확인

## 진행 상황
- 2026-10-12 06:42 전부 완료: 시드 2, 3 x 5개 묶음 (10번), 시드 1 재실행 x 3개 묶음. 결과는 `results/` 와 `docs/05_train_evaluate.md`

## Kaggle 노트북 관리 (2026-10-12)
- 저장소 노트북 `kaggle/02_seeds.ipynb`이 기준이다. 수정은 `kaggle/build_notebook.py`로 저장소에서 하고, Kaggle에는 File → Import Notebook → GitHub(브랜치 선택)로 가져온다. Kaggle 계정은 GitHub와 연결됨 (비공개 저장소 포함)
- Kaggle 편집 화면에서 직접 셀을 덧붙이지 않는다 (10/12 새벽에 그렇게 했다가 두 노트북이 어긋났음)
- 셀 8(시드 1 재실행), 셀 9(짝지어 비교 재평가)는 `RUN_SEED1`, `RUN_PAIRED`를 True로 바꿀 때만 돈다
