# syntax=docker/dockerfile:1.7
# Multi-stage build: uv resolves the locked deps in a builder, the runtime image only
# carries the virtualenv and source, and runs as a non-root user.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first (cached layer), project second.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LOG_JSON=true
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status != 200)"]
CMD ["docs-assistant-api"]
