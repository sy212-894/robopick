"""Kaggle API 호출 (실험 전용, 사용자 흐름에서는 쓰지 않는다).

한계 보완 실험 노트북(kaggle/05~07)을 올리고, 상태·로그를 보고, 결과 파일을 받을 때 쓴다. Kaggle API는 별도 환경
(kaggle-cli, 파이썬 3.12)의 kaggle_helper.py를 하위 프로세스로 불러 쓴다. 도구 서버 환경(파이썬 3.10)에는 새 토큰을
지원하는 kaggle 1.8+를 설치할 수 없어서다. 토큰은 kaggle 패키지가 ~/.kaggle/access_token에서 직접 읽는다.

10/13에 만든 "승인 뒤 Kaggle 대신 학습"(launch·status·stop·resume)은 10/17에 뺐다. 사용자는 학습 키트를 받아
자기 환경에서 학습한다 (docs/13_kaggle_runner.md).

사용 예: run_helper("status", slug="qkdsy482/curation-b60-round2a")
설정 (환경 변수): KAGGLE_PYTHON (kaggle-cli 환경의 python)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "kaggle_helper.py"
KAGGLE_PYTHON = os.environ.get("KAGGLE_PYTHON", "C:/miniconda3/envs/kaggle-cli/python.exe")
ACCELERATOR = "NvidiaTeslaT4"


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
