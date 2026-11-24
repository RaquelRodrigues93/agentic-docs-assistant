# 00 — Overview and architecture

Status: `accepted` (Phase 0)

## Problem

Developers ask the same questions about a project's docs again and again, and when the docs
are wrong or missing something, the feedback rarely turns into a tracked issue. We want an
assistant that answers from the docs **with verifiable citations** and can turn a gap it
finds into a GitHub issue, **but never acts on the outside world without a human's approval**.

## Goals

- Answer questions about a Markdown docs corpus, citing the file and section for every claim.
- Refuse clearly when a question is outside the corpus or the assistant's scope.
- Draft external actions (create a GitHub issue), pause, and run them only after approval.
- Be provider-agnostic (AWS Bedrock in prod, Ollama locally) and fully traceable.
- Measure quality with a golden dataset in CI.

## Non-goals

- Multi-tenant auth, user accounts, chat UI (the API is the product; curl/Swagger is the client).
- Answering from the open web or from code (docs only).
- Write actions other than creating issues (the design allows more; we only ship one).
- Streaming responses (possible later; not needed to show the architecture).

## Knowledge base

`docs/` contains the documentation of **Driftwood**, a fictional self-hosted feature-flag
service (about 12 pages: overview, quickstart, configuration, authentication, SDKs, REST API,
deployment, observability, troubleshooting, FAQ). It is fictional so that:
the model cannot answer from pre-training (it must retrieve), there are no licensing issues,
and the eval set stays stable. The corpus contains **deliberate gaps** (for example, the
authentication page has no refresh-token section) that drive the "open an issue" demo.

## Architecture

```mermaid
flowchart LR
    client([Client / curl]) -->|HTTP| api[FastAPI service]
    api --> graph[LangGraph agent]
    graph <-->|checkpoints| ckpt[(SQLite checkpointer)]
    graph -->|structured output| llm{{LLM provider<br/>Bedrock · Ollama}}
    graph -->|MCP client · streamable HTTP| mcp[MCP server]
    mcp -->|search_docs| qdrant[(Qdrant)]
    mcp -->|create_github_issue| gh[GitHub API]
    ingest[[Ingestion CLI]] -->|chunks + embeddings| qdrant
    graph -. OTel traces .-> phoenix[Arize Phoenix]
```

Runtime components (containers): `api`, `mcp-server`, `qdrant`, `phoenix` (local only).

## Package layout

The brief suggests top-level packages `src/api`, `src/agent`, … We use a single
installable package, `src/docs_assistant/{api,agent,mcp_server,rag,llm,guardrails,observability}`,
because generic top-level names like `api` and `agent` collide with other distributions
and break `mypy`/imports. The structure stays the same, just one level deeper.

## Decision log

| ID | Decision | Why | Alternatives considered |
|---|---|---|---|
| D1 | **Python 3.13** (`>=3.13,<3.15`) | Newest version supported by the whole stack: `arize-phoenix-otel` is `<3.16`, `openinference-instrumentation-langchain` is `<3.15`. | 3.12 (works, older); 3.14 (blocked by the instrumentation package). |
| D2 | **MCP SDK 2.x used directly** (`mcp>=2.3`: `MCPServer`, `mcp.Client`); **no `langchain-mcp-adapters`** | The adapter (0.3.2) pins `mcp<2`, which would tie us to the previous major. We do not need LangChain tool binding (see D3), so a thin typed client over `mcp.Client` is ~50 lines. `mcp.Client` can also connect to an `MCPServer` **in-process**, which gives clean tests. | `langchain-mcp-adapters` + `mcp 1.30` (more ecosystem glue, older SDK). |
| D3 | **The planner picks tools through structured output, not native LLM tool calling** | The plan node returns a Pydantic `PlannerDecision` (a discriminated union of actions). This (a) works the same on Bedrock and Ollama, (b) lets guardrails check a typed decision *before* anything runs, and (c) avoids forced `tool_choice`, which current Claude models reject (400). Tools still run **through MCP**; only the choice is made by structured output. | ReAct with `bind_tools` (less control, provider quirks). |
| D4 | **Local embeddings (`fastembed`, `BAAI/bge-small-en-v1.5`, 384-d) by default**; Bedrock Titan available through config | Retrieval evals run for free and offline in CI on every PR, ingestion has no cloud dependency, and the same model runs in dev, CI and prod. | Titan everywhere (CI needs AWS credentials on every PR). |
| D5 | **SQLite checkpointer** (`langgraph-checkpoint-sqlite`, async) by default; Postgres optional | Zero infra locally. On ECS the trade-off (state lost on task replacement) is documented in spec 10; a Postgres checkpointer is a config switch. | Postgres from day one (RDS cost and ops for a demo). |
| D6 | **MCP over streamable HTTP** between containers | Same transport in docker-compose and ECS (sidecar on localhost); stdio would tie the server's lifecycle to the API process. | stdio subprocess. |
| D7 | **Bedrock model IDs are configuration only** | IDs and cross-region inference profiles change; they are verified with `aws bedrock list-inference-profiles` at deploy time, never hard-coded. Defaults: Claude Sonnet (agent), Claude Haiku (eval judge), region `us-east-1`. | — |
| D8 | **Issues go to a separate sandbox repo**, dry-run by default | Demo and test issues never clutter the portfolio repo; the token is a fine-grained PAT scoped to that one repo with Issues read/write only. | Issues on the main repo. |
| D9 | **CI: retrieval evals on every PR; LLM-judge evals gated** | Retrieval evals are free (D4). The judge runs on Bedrock through GitHub OIDC only on `main`, on a `run-llm-evals` label, or by manual dispatch, which keeps costs bounded and keeps credentials away from fork PRs. | Judge on every PR. |

## Cross-cutting conventions

- Every LLM output and tool I/O is a Pydantic model. No regex or JSON parsing of free text.
- Every external call (LLM, Qdrant, MCP, GitHub) has an explicit timeout, and retries with
  backoff only where the call is idempotent.
- Prompts live in `prompts/` as versioned files and are loaded by name and version (spec 02).
- Settings come only from env vars (`docs_assistant.config.Settings`); `.env.example` documents them.

## Acceptance criteria (Phase 0)

- [ ] `docker compose up` starts `api`, `qdrant`, `phoenix`; `GET /health` → `200 {"status":"ok"}`.
- [ ] `GET /health/ready` → `200` when Qdrant is reachable, `503` otherwise.
- [ ] `uv run ruff check .`, `uv run mypy`, `uv run pytest` pass locally and in CI.
- [ ] All specs in this folder exist and are reviewed.
