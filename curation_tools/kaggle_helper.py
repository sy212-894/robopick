"""Kaggle API 도우미. kaggle 2.x가 깔린 별도 환경(kaggle-cli, 파이썬 3.12)에서 실행된다.

도구 서버(curation 환경, 파이썬 3.10)는 새 토큰을 지원하는 kaggle 1.8+를 설치할 수 없어서, 이 스크립트를
하위 프로세스로 불러 JSON 한 줄로 결과를 받는다 (kaggle_runner.run_helper). 토큰은 ~/.kaggle/access_token
또는 KAGGLE_API_TOKEN 환경 변수에서 kaggle 패키지가 직접 읽는다. 이 스크립트는 토큰 값을 출력하지 않는다.

명령 (python kaggle_helper.py <명령> <JSON 인자>)
- push   {"folder", "accelerator"}       노트북 폴더(kernel-metadata.json 포함)를 올려 실행
- status {"slug"}                         실행 상태 (RUNNING, COMPLETE, ERROR, CANCEL_* 등)
- logs   {"slug", "seconds"}              실행 중 로그를 정해진 초만 읽고 끊는다 (stdout 줄 목록)
- cancel {"session_id"}                   실행 중인 세션 중단
- quota  {}                               GPU 사용량과 초기화 시각
- output {"slug", "dest", "pattern"}      끝난 실행의 출력 파일 받기
"""
from __future__ import annotations

import json
import sys
import time

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (ApiCancelKernelSessionRequest,
                                                         ApiGetAcceleratorQuotaStatisticsRequest,
                                                         ApiGetKernelSessionLogsStreamRequest,
                                                         ApiGetKernelSessionStatusRequest)


def _api() -> KaggleApi:
    api = KaggleApi()
    api.authenticate()
    return api


def _split(slug: str) -> tuple[str, str]:
    user, _, name = slug.partition("/")
    return user, name


def push(a: dict) -> dict:
    api = _api()
    r = api.kernels_push(a["folder"], acc=a.get("accelerator"))
    return {"ref": getattr(r, "ref", None), "url": getattr(r, "url", None),
            "version": getattr(r, "version_number", None), "error": getattr(r, "error", None) or None}


def status(a: dict) -> dict:
    user, name = _split(a["slug"])
    with _api().build_kaggle_client() as k:
        r = ApiGetKernelSessionStatusRequest()
        r.user_name, r.kernel_slug = user, name
        d = k.kernels.kernels_api_client.get_kernel_session_status(r).to_dict()
    return {"status": d.get("status"), "failure": d.get("failureMessage")}


def logs(a: dict) -> dict:
    """실행 중이면 서버가 보내는 로그 흐름(SSE)을 정해진 초만 읽는다. 처음부터 다시 보내 주므로 진행 상황을 모두 얻는다.
    끝난 실행이면 저장된 로그(JSON)가 온다."""
    user, name = _split(a["slug"])
    out: list[str] = []
    with _api().build_kaggle_client() as k:
        hc = k.kernels.kernels_api_client._client
        hc._init_session()
        r = ApiGetKernelSessionLogsStreamRequest()
        r.user_name, r.kernel_slug, r.wait_for_logs_url_seconds = user, name, 20
        req = hc._prepare_request("kernels.KernelsApiService", "GetKernelSessionLogsStream", r)
        # 서버는 로그 주소를 최대 20초 기다린 뒤 응답하고, 새 출력이 없으면 한동안 아무것도 보내지 않는다
        resp = hc._session.send(req, stream=True, timeout=(10, 30))
        kind = resp.headers.get("content-type", "")
        resp.encoding = "utf-8"  # 서버가 charset을 안 붙여서 requests가 latin-1로 읽으면 한글 로그가 깨진다
        t0 = time.time()
        try:
            if "event-stream" in kind:
                try:
                    for line in resp.iter_lines(decode_unicode=True):
                        if line and line.startswith("data:"):
                            try:
                                ev = json.loads(line[5:])
                                out += [x for x in ev.get("data", "").splitlines() if x.strip()]
                            except json.JSONDecodeError:
                                pass
                        if time.time() - t0 > float(a.get("seconds", 8)):
                            break
                except Exception:  # 읽는 중 시간 초과: 그때까지 받은 줄로 판단한다
                    pass
            else:
                for ev in json.loads(resp.content or b"[]"):
                    out += [x for x in ev.get("data", "").splitlines() if x.strip()]
        finally:
            resp.close()
    return {"lines": out, "live": "event-stream" in kind}


def cancel(a: dict) -> dict:
    with _api().build_kaggle_client() as k:
        r = ApiCancelKernelSessionRequest()
        r.kernel_session_id = int(a["session_id"])
        d = k.kernels.kernels_api_client.cancel_kernel_session(r).to_dict()
    return {"error": d.get("errorMessage") or None}


def _hours(v) -> float | None:
    return round(v.total_seconds() / 3600, 2) if v is not None else None


def quota(a: dict) -> dict:
    # to_dict()는 시간 값을 글자로 바꿀 때 '일' 단위를 빠뜨린다 (1일 3시간 → '3시간'). 원래 timedelta를 읽는다
    with _api().build_kaggle_client() as k:
        r = k.kernels.kernels_api_client.get_accelerator_quota_statistics(ApiGetAcceleratorQuotaStatisticsRequest())
    g = r.gpu_quota
    refresh = r.quota_refresh_time
    return {"gpu_used_hours": _hours(g.time_used) or 0.0, "gpu_allowed_hours": _hours(g.total_time_allowed),
            "refresh": refresh.isoformat() + "Z" if hasattr(refresh, "isoformat") else refresh}  # UTC


def output(a: dict) -> dict:
    api = _api()
    try:
        api.kernels_output(a["slug"], a["dest"], file_pattern=a.get("pattern"), force=True, quiet=True)
    except Exception as e:  # 파일을 받은 뒤 로그 파일 목록 요청이 한도에 걸릴 때가 있다 (429). 받은 파일로 판단한다
        return {"warning": f"{type(e).__name__}: {str(e)[:200]}"}
    return {}


COMMANDS = {"push": push, "status": status, "logs": logs, "cancel": cancel, "quota": quota, "output": output}

if __name__ == "__main__":
    cmd, arg = sys.argv[1], json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")
    try:
        res = {"ok": True, **COMMANDS[cmd](arg)}
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    print(json.dumps(res, ensure_ascii=False))
