"""Application settings, loaded from environment variables (and `.env` in development).

Every external dependency is configured here so that nothing is hard-coded in modules.
Later phases extend this model; see specs/ for the full list of settings per component.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case env vars (e.g. `QDRANT_URL`)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["local", "ci", "aws"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(default=False, description="Emit JSON logs (enable in containers).")

    # Dependencies checked by the readiness probe.
    qdrant_url: HttpUrl = HttpUrl("http://localhost:6333")
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached; override in tests via DI)."""
    return Settings()
