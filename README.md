# Agentic Docs Assistant

An agentic assistant that answers questions about a repository's documentation with
source citations (RAG over Qdrant), and can take actions such as opening a GitHub issue,
but only after a human approves them. Built with LangGraph, a custom MCP server, FastAPI,
and AWS Bedrock.

> **Status: Phase 0 (specs and skeleton).** Design lives in [`specs/`](specs/README.md).
> The full README (architecture diagram, eval results, technical decisions) lands in Phase 5.

## Quickstart (local)

Requirements: Docker, [uv](https://docs.astral.sh/uv/) 0.13+.

```bash
cp .env.example .env
docker compose up --build        # API :8000, Qdrant :6333, Phoenix UI :6006
curl localhost:8000/health       # {"status":"ok","version":"0.1.0"}
curl localhost:8000/health/ready # checks Qdrant
```

Development without Docker:

```bash
uv sync
uv run docs-assistant-api        # serves on :8000
uv run pytest && uv run ruff check . && uv run mypy
```

## Roadmap

| Phase | Scope |
|---|---|
| 0 | Specs, skeleton, health endpoint, docker-compose (Qdrant, Phoenix) |
| 1 | RAG ingestion and retrieval with citations, LangGraph agent, `/chat` |
| 2 | MCP server (`search_docs`, `create_github_issue`), human-in-the-loop approvals, guardrails |
| 3 | Phoenix tracing, golden-dataset evals, CI |
| 4 | Terraform for ECS Fargate and Bedrock, cost notes |
| 5 | Portfolio polish |

## License

MIT
