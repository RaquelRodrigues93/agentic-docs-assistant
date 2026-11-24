"""Pydantic response models for the HTTP API."""

from typing import Literal

from pydantic import BaseModel, Field

DependencyState = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    """Liveness: the process is up and serving requests."""

    status: Literal["ok"] = "ok"
    version: str


class DependencyStatus(BaseModel):
    name: str
    status: DependencyState
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness: required dependencies are reachable."""

    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyStatus] = Field(default_factory=list)
