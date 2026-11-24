from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from docs_assistant import __version__
from docs_assistant.api import health as health_module
from docs_assistant.api.main import create_app
from docs_assistant.api.schemas import DependencyStatus
from docs_assistant.config import Settings, get_settings

SETTINGS = Settings(qdrant_url="http://qdrant.test:6333", dependency_timeout_seconds=0.5)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def stub_qdrant(monkeypatch: pytest.MonkeyPatch, result: DependencyStatus) -> None:
    async def fake(settings: Settings) -> DependencyStatus:
        return result

    monkeypatch.setattr(health_module, "check_qdrant", fake)


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


async def test_ready_returns_200_when_dependencies_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_qdrant(monkeypatch, DependencyStatus(name="qdrant", status="ok"))
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_ready_returns_503_when_a_dependency_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_qdrant(monkeypatch, DependencyStatus(name="qdrant", status="unavailable", detail="x"))
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


async def test_check_qdrant_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://qdrant.test:6333/readyz"
        return httpx.Response(200)

    result = await health_module.check_qdrant(SETTINGS, httpx.MockTransport(handler))
    assert result.status == "ok"


async def test_check_qdrant_reports_http_error_status() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    result = await health_module.check_qdrant(SETTINGS, transport)
    assert (result.status, result.detail) == ("unavailable", "HTTP 500")


async def test_check_qdrant_reports_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await health_module.check_qdrant(SETTINGS, httpx.MockTransport(handler))
    assert (result.status, result.detail) == ("unavailable", "ConnectError")
