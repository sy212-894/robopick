"""한계 보완 실험 노트북 3개 생성 (docs/10_robustness.md, 2026-10-13).

B 노트북(04_budget)과 같은 방식: Square 노트북(03_square.ipynb)의 설치·데이터·학습·평가 셀을 그대로 쓰고
계획·실행 목록 셀만 바꾼다. 평가는 200 epoch 30회 + 400 epoch 100회, 물체 위치·행동 난수를 시험마다 12345+i로 고정.
Kaggle API로 올려 서버에서 실행한다 (브라우저 세션이 아니라 자리 비움 종료가 없다).

- 05_seeds45.ipynb: 예산 150 본 실험 계획(c15466d53a01cedb)으로 선별·무작위·전체 x 시드 4, 5 (한계 1)
- 06_b60_round1.ipynb: 예산 60 계획으로 우리 선별·무작위·길이만·그리퍼만 x 시드 1~3 (한계 2·9, 1차)
- 07_b60_round2.ipynb: 예산 60 계획으로 나머지 6묶음 x 시드 1~3 (2차, GPU 초기화 뒤)

사용: python kaggle/build_extra_notebooks.py .
"""
import json
import sys
from pathlib import Path

RUNS = Path("C:/curation-data/runs")
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo.resolve()))
from curation_tools.train_eval import compact_plan  # noqa: E402
base = json.loads((repo / "kaggle/03_square.ipynb").read_text(encoding="utf-8"))
cells = {c["id"]: c for c in base["cells"]}


def code(cid, text):
    return {"cell_type": "code", "id": cid, "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def md(cid, text):
    return {"cell_type": "markdown", "id": cid, "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def build(name: str, title: str, run_id: str, outdir: str, jobs: list[tuple[str, int]], about: str) -> None:
    # 계획 파일에서 압축 문자열을 새로 만든다. 10/11에 만든 본 실험의 plan_b64.txt는 데이터 이름·다운로드 경로가 없는 옛 형식이라
    # 그대로 쓰면 데이터 셀이 실패한다. 지문·묶음·설정은 plan.json 그대로라 바뀌지 않는다
    plan_b64 = compact_plan(json.loads((RUNS / run_id / "plan" / "plan.json").read_text(encoding="utf-8")))
    intro = md("intro", f"# {title}\n\n{about.strip()}\n")
    s3 = code("s3", f"""
# 3. 학습 계획 + 실행 목록
MODE = 'main'
PLAN_B64 = '{plan_b64}'
import json, base64, zlib, os
PLAN = json.loads(zlib.decompress(base64.b64decode(PLAN_B64)))
SETS = {{k: [f'demo_{{i}}' for i in v] for k, v in PLAN['sets'].items()}}
OUTDIR = '/kaggle/working/{outdir}'
CKPT = f'{{OUTDIR}}/ckpt_{{PLAN["fp"]}}'
os.makedirs(CKPT, exist_ok=True)
JOBS = {jobs!r}
# 1주차 최종 평가 기준: 400 epoch 시험 100개 (계획의 rollout_n과 상관없이 고정), 200 epoch 30개
EVAL_N = {{PLAN['config']['early_eval_epoch']: 30, PLAN['config']['num_epochs']: 100}}
print('[결과] 데이터', PLAN['dataset'], '| 지문', PLAN['fp'], '| 실행', len(JOBS), JOBS)
print('[결과] 설정', PLAN['config'], '| 평가', EVAL_N)
""")
    order = [intro, cells["s1"], cells["s2"], s3, cells["s4"], cells["s5"], cells["s6"], cells["s7"]]
    nb = {"cells": order, "metadata": base["metadata"], "nbformat": 4, "nbformat_minor": 5}
    (repo / f"kaggle/{name}.ipynb").write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, len(jobs), "실행")


COMMON = """
- 평가: 200 epoch 30회 + 400 epoch 100회. 물체 위치와 행동 샘플링 난수를 시험마다 12345+i로 고정 (A·B와 같은 위치·같은 난수)
- 판정 규칙은 `docs/10_robustness.md`에 결과 보기 전에 적고 커밋했다
- 결과는 실행 하나가 끝날 때마다 출력 폴더의 `results_main_<지문>.json`에 저장된다
"""

build("05_seeds45", "한계 1: 시드 4·5 추가 (예산 150)", "R-20261011-select-main", "seeds45",
      [(n, s) for s in (4, 5) for n in ("curated_150", "random_150", "train")],
      "- 본 실험 계획(지문 c15466d53a01cedb)으로 학습 시드만 4, 5로 바꿔 선별·무작위·전체를 학습한다\n" + COMMON)
build("06_b60_round1", "예산 60 기준선 비교 1차", "R-20261013-select-b60", "b60",
      [(n, s) for s in (1, 2, 3) for n in ("curated_60", "random_60", "length_60", "gripper_60")],
      "- 예산 60 계획(R-20261013-select-b60, 묶음 12개를 결과 보기 전에 확정)에서 1차 4묶음을 학습한다\n" + COMMON)
build("07_b60_round2", "예산 60 기준선 비교 2차", "R-20261013-select-b60", "b60",
      [(n, s) for s in (1, 2, 3) for n in ("nolength3_60", "idle_60", "path_60", "stratified_random_60", "diversity_60", "longest_60")],
      "- 예산 60 계획의 2차 6묶음. 1차와 같은 계획이고 묶음은 1차 결과를 보기 전에 정했다\n" + COMMON)
