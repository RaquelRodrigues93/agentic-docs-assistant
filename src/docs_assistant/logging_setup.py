"""Structured logging setup (structlog). JSON in containers, pretty console locally."""

import logging

import structlog


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure structlog and the stdlib root logger once at process start."""
    logging.basicConfig(format="%(message)s", level=level)
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )
