# 03 — MCP server

Status: `accepted` · Phase: 2

## Goals

- Our own MCP server, built on the official Python SDK **2.x** (`mcp.server.mcpserver.MCPServer`),
  exposing `search_docs` and `create_github_issue` with typed input and output schemas.
- The agent consumes these tools **only** through an MCP client (`mcp.Client`), never by
  importing the tool functions.
- Safe by default: dry-run on, one allowlisted repository, a least-privilege token.

## Non-goals

- MCP resources and prompts, OAuth for the MCP server (it is only reachable on the internal
  network or localhost), and tools other than the two below.

## Transport and deployment

- Streamable HTTP at `http://<host>:8001/mcp` (`MCPServer.run("streamable-http", ...)`).
  Runs as its own container (`mcp-server`) in docker-compose and as a sidecar in the ECS task.
- DNS-rebinding protection stays on; allowed hosts are configured for `mcp-server` and `localhost`.
- Tests connect in-process: `async with Client(server) as client:` (no network).

## Tools

### `search_docs`

Read-only. Annotations: `readOnlyHint=true`, `openWorldHint=false`.

```python
class SearchDocsInput(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    top_k: int = Field(default=6, ge=1, le=10)

class RetrievedChunk(BaseModel):
    chunk_id: str
    source: str            # "docs/authentication.md"
    section: str           # "Authentication > API keys"
    text: str
    score: float

class SearchDocsOutput(BaseModel):
    chunks: list[RetrievedChunk]
```

Delegates to `docs_assistant.rag.retriever` (spec 04). Qdrant timeout 5 s, and it returns an MCP tool
error (`isError=true`) on failure, never an empty success.

### `create_github_issue`

Side-effecting. Annotations: `destructiveHint=false`, `idempotentHint=true` (keyed),
`openWorldHint=true`. **Classified as requiring approval** in the agent's guardrail
config (spec 06). The server does not trust the agent to have asked for approval; it
only enforces its own checks (repo allowlist, schema, idempotency).

```python
class CreateIssueInput(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    body: str = Field(min_length=20, max_length=5000)
    labels: list[Literal["documentation", "bug", "enhancement"]] = ["documentation"]
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")   # the approved action_id

class CreateIssueOutput(BaseModel):
    dry_run: bool
    repo: str
    issue_number: int | None
    url: str | None
    payload: dict[str, object]       # exactly what was, or would have been, sent to GitHub
```

Behavior:
- The target repo comes **only** from server config (`GITHUB_REPO`). It is not a tool argument,
  so the LLM cannot redirect writes.
- `GITHUB_DRY_RUN=true` (the default): returns the payload and calls nothing.
- Live mode: `POST /repos/{repo}/issues` through `httpx` (timeout 10 s, up to 2 retries on 5xx/429
  honoring `Retry-After`). The body gets a hidden footer `<!-- docs-assistant:idempotency_key=... -->`.
  Before creating, the server searches for an open issue containing that key and returns it if found,
  so retries never create duplicates.
- Errors (401/403/404/422 from GitHub) become MCP tool errors with a sanitized message (no token, no raw response).

## Client side (`docs_assistant.agent.mcp_client`)

- `McpToolClient` wraps `mcp.Client` with typed methods `search_docs(...) -> SearchDocsOutput`
  and `create_github_issue(...) -> CreateIssueOutput`. It validates `structuredContent` against the
  output models (and raises on `isError`).
- Before calling, it enforces the tool allowlist (spec 06). Per-call read timeout:
  10 s for search, 20 s for issue creation.
- One client session per API process, opened in the lifespan; it reconnects on transport errors.

## Configuration

`MCP_SERVER_URL`, `GITHUB_REPO` (`owner/name`, validated), `GITHUB_TOKEN` (fine-grained PAT, Issues R/W
on that repo only; optional in dry-run), `GITHUB_DRY_RUN` (default `true`), `MCP_HOST`, `MCP_PORT`.

## Acceptance criteria

- `list_tools` returns exactly the two tools, with JSON input and output schemas.
- In-process tests: `search_docs` returns chunks for a seeded collection; dry-run issue creation
  calls nothing (asserted with an `httpx.MockTransport` that fails on any request); live mode sends the
  expected payload to the mock; a duplicate `idempotency_key` returns the existing issue; a GitHub 403
  becomes a tool error with no token in the message.
- The server refuses to start in live mode without `GITHUB_TOKEN` and `GITHUB_REPO`.
