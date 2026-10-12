"""설정: webapi/.env (git에 올리지 않음)를 읽는다. 없는 값은 아래 기본값.

DIFY_API_BASE   Dify 앱 API 주소 (설치형 Dify 기본: http://localhost/v1)
DIFY_API_KEY    Dify 앱 "API 접근"에서 발급한 키 (app-로 시작). 비어 있으면 Dify 기능만 꺼진다
TOOLS_ADDR      MCP 도구 서버 주소 (curation_tools.server, 127.0.0.1:8800)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class Settings:
    dify_api_base: str
    dify_api_key: str
    tools_host: str
    tools_port: int
    runs_root: Path
    events_path: Path
    web_dist: Path


def load() -> Settings:
    env = {**_read_env(HERE / ".env"), **{k: v for k, v in os.environ.items() if k.startswith(("DIFY_", "TOOLS_"))}}
    host, _, port = env.get("TOOLS_ADDR", "127.0.0.1:8800").partition(":")
    return Settings(
        dify_api_base=env.get("DIFY_API_BASE", "http://localhost/v1").rstrip("/"),
        dify_api_key=env.get("DIFY_API_KEY", ""),
        tools_host=host,
        tools_port=int(port or 8800),
        runs_root=Path(env.get("RUNS_ROOT", "C:/curation-data/runs")),
        events_path=Path(env.get("EVENTS_PATH", "C:/curation-data/logs/events.jsonl")),
        # 화면 빌드 결과. OneDrive 안(web/dist)에 쓰면 빌드가 죽어서 밖에 둔다 (web/vite.config.ts와 같은 값)
        web_dist=Path(env.get("WEB_DIST", "C:/curation-data/web-dist")),
    )
