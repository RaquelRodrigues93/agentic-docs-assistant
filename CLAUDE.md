# CLAUDE.md — project conventions

Agentic docs assistant: FastAPI + LangGraph agent, RAG over Qdrant, our own MCP server,
human-in-the-loop approvals, Bedrock/Ollama providers, Phoenix tracing, evals in CI.

## Ground rules

- **Specs first.** `specs/` is the source of truth. Read the relevant spec before changing a
  component; if an interface or acceptance criterion changes, update the spec in the same change.
  Record non-obvious choices in the decision log (`specs/00-overview.md`).
- **Check library APIs before using them.** LangGraph, the MCP SDK (2.x: `MCPServer`, `mcp.Client`;
  `FastMCP` no longer exists) and langchain-aws change often. Inspect the installed package or the
  official docs; do not write from memory.
- **Phased delivery.** Work phase by phase (see README roadmap); stop at the end of each phase for review.

## Code

- Python 3.13, `uv` for everything (`uv sync`, `uv run ...`, `uv add ...`). Package: `src/docs_assistant`.
- Type hints everywhere; `mypy --strict` must pass. Small modules, clear names, no clever metaprogramming.
- **Structured everything**: LLM outputs, tool inputs and outputs, API bodies are Pydantic models.
  Never parse free-form LLM text.
- **Prompts are files**: `prompts/<name>/v<N>.md`; never inline prompt strings in code. A released
  version is immutable; to change a prompt, add `v<N+1>` and update `ACTIVE_PROMPTS`.
- **Every external call has a timeout** (LLM, Qdrant, MCP, GitHub), and retries only when the call is idempotent.
- **No provider SDK imports outside `docs_assistant.llm`**; no Qdrant imports outside `docs_assistant.rag`.
- **Side effects only after approval**: tools that write go through `REQUIRES_APPROVAL` (spec 06).
- Config only through `docs_assistant.config.Settings` (env vars). New settings go in `.env.example`.
- Logging: `structlog`, with key-value events (`log.info("approval.decided", run_id=...)`), no f-string messages, never log secrets.

## Tests

- `uv run pytest` must not need network, Docker, or an LLM. Use the fake LLM, the in-process MCP
  server (`mcp.Client(server)`), Qdrant `:memory:`, and `httpx.MockTransport`.
- Tests that need real services are marked `@pytest.mark.integration` and are skipped by default.
- Every bug fix comes with a test that fails without it.

## Commands

```bash
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest   # pre-commit gate
docker compose up --build                                                    # local stack
```

## Git

- Small, thematic commits with imperative English subject lines; one concern per commit.
- No AI co-author trailers in commits or PRs.
- Never commit `.env`, tokens, `*.tfstate`, or `*.tfvars`.
