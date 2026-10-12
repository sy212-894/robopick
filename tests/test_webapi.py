"""웹 중계 서버(webapi) 테스트: 상태 확인 API. 실제 Dify·도구 서버 대신 가짜 응답을 쓴다."""
import httpx
import pytest
from starlette.testclient import TestClient

from webapi import app as A
from webapi.config import Settings


def _settings(tmp_path, key=""):
    return Settings(dify_api_base="http://dify.test/v1", dify_api_key=key, tools_host="127.0.0.1", tools_port=1,
                    runs_root=tmp_path, events_path=tmp_path / "events.jsonl", web_dist=tmp_path / "dist")


def test_health_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    r = TestClient(A.app).get("/api/health").json()
    assert r["dify"] == {"ok": False, "detail": "API 키 없음 (webapi/.env의 DIFY_API_KEY)"}
    assert r["tools"]["ok"] is False  # 1번 포트에는 아무것도 없다


@pytest.mark.parametrize("status,ok,detail", [(200, True, "시범데이터 선별 에이전트"), (401, False, "API 키가 맞지 않음")])
def test_health_dify_key(tmp_path, monkeypatch, status, ok, detail):
    monkeypatch.setattr(A, "settings", _settings(tmp_path, key="app-test"))
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(status, json={"name": "시범데이터 선별 에이전트"})

    real = httpx.AsyncClient
    monkeypatch.setattr(A.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    r = TestClient(A.app).get("/api/health").json()
    assert r["dify"] == {"ok": ok, "detail": detail}
    assert seen["auth"] == "Bearer app-test"


def test_spa_without_build(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "settings", _settings(tmp_path))
    r = TestClient(A.app).get("/demo")
    assert r.status_code == 404 and "빌드" in r.json()["detail"]
