"""중계 서버 (Starlette). 1단계: 상태 확인만. 채팅·승인·기록·결과 API는 2단계에서 붙인다.

실행: python -m webapi  (curation-agent 폴더에서, conda env curation) → http://127.0.0.1:8900
개발 중 화면은 web/에서 npm run dev (http://localhost:5173, /api는 이 서버로 넘어옴)
"""
from __future__ import annotations

import asyncio

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from webapi.config import Settings, load

settings: Settings = load()


async def _check_dify() -> dict:
    """Dify에 닿는지, 그리고 API 키가 맞는지 본다 (/v1/info는 키가 맞아야 200)."""
    if not settings.dify_api_key:
        return {"ok": False, "detail": "API 키 없음 (webapi/.env의 DIFY_API_KEY)"}
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{settings.dify_api_base}/info", headers={"Authorization": f"Bearer {settings.dify_api_key}"})
        if r.status_code == 200:
            return {"ok": True, "detail": r.json().get("name", "연결됨")}
        if r.status_code == 401:
            return {"ok": False, "detail": "API 키가 맞지 않음"}
        return {"ok": False, "detail": f"Dify 응답 {r.status_code}"}
    except httpx.HTTPError as e:
        return {"ok": False, "detail": f"Dify에 연결할 수 없음 ({type(e).__name__})"}


async def _check_tools() -> dict:
    """MCP 도구 서버 포트가 열려 있는지 본다."""
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(settings.tools_host, settings.tools_port), timeout=2)
        w.close()
        await w.wait_closed()
        return {"ok": True, "detail": f"{settings.tools_host}:{settings.tools_port}"}
    except (OSError, asyncio.TimeoutError):
        return {"ok": False, "detail": f"{settings.tools_host}:{settings.tools_port} 응답 없음"}


async def health(request: Request) -> JSONResponse:
    dify, tools = await asyncio.gather(_check_dify(), _check_tools())
    return JSONResponse({"dify": dify, "tools": tools})


async def spa(request: Request):
    """빌드한 화면(web/dist)이 있으면 그 index.html을 돌려준다 (새로고침해도 /demo 같은 주소가 열리게)."""
    index = settings.web_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "화면이 빌드되지 않았습니다. web 폴더에서 npm run dev 또는 npm run build"}, status_code=404)


routes = [Route("/api/health", health)]
app = Starlette(routes=routes)
if (settings.web_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist / "assets"), name="assets")
app.add_route("/{path:path}", spa)
