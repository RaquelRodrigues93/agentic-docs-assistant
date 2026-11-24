"""Liveness and readiness endpoints."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Response, status

from docs_assistant import __version__
from docs_assistant.api.schemas import DependencyStatus, HealthResponse, ReadinessResponse
from docs_assistant.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe. Never touches dependencies, so it stays cheap and reliable."""
    return HealthResponse(version=__version__)


async def check_qdrant(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> DependencyStatus:
    """Ping Qdrant's readiness endpoint with a short timeout. `transport` is for tests."""
    url = f"{str(settings.qdrant_url).rstrip('/')}/readyz"
    try:
        async with httpx.AsyncClient(
            timeout=settings.dependency_timeout_seconds, transport=transport
        ) as client:
            resp = await client.get(url)
        if resp.is_success:
            return DependencyStatus(name="qdrant", status="ok")
        detail = f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        detail = type(exc).__name__
    return DependencyStatus(name="qdrant", status="unavailable", detail=detail)


@router.get("/health/ready", response_model=ReadinessResponse)
async def ready(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> ReadinessResponse:
    """Readiness probe: 200 when all dependencies are reachable, 503 otherwise."""
    deps = [await check_qdrant(settings)]
    is_ready = all(d.status == "ok" for d in deps)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if is_ready else "not_ready", dependencies=deps)
