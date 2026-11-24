"""FastAPI application factory and entrypoint."""

import uvicorn
from fastapi import FastAPI

from docs_assistant import __version__
from docs_assistant.api.health import router as health_router
from docs_assistant.config import get_settings
from docs_assistant.logging_setup import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI app. Kept as a factory so tests get a fresh instance."""
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    app = FastAPI(title="Agentic Docs Assistant", version=__version__)
    app.include_router(health_router)
    return app


def run() -> None:
    """Console entrypoint: `uv run docs-assistant-api`."""
    uvicorn.run(  # binds all interfaces for containers; S104 is expected here
        "docs_assistant.api.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=8000,
    )
