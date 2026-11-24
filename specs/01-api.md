# 01 — HTTP API

Status: `accepted` · Phases: 0 (health), 1 (chat), 2 (runs/approvals, auth)

## Goals

- Expose the agent as an async FastAPI service with typed (Pydantic) requests and responses.
- Make the human-in-the-loop lifecycle explicit: a run can end **completed**, **refused**,
  **failed**, or pause as **awaiting_approval** until someone approves or rejects it.
- Fail predictably: one error envelope, correct status codes, no stack traces in responses.

## Non-goals

- Streaming (SSE/WebSocket), multi-user identity, rate limiting beyond a simple per-process limit.

## Concepts

- **Thread**: a conversation (LangGraph `thread_id`). Clients keep it to ask follow-ups.
- **Run**: one user message processed by the graph within a thread. A run is created per
  `POST /chat` and has a stable `run_id` (UUID4) used by the approval endpoints.
- **Pending action**: a drafted external action waiting for a decision. It carries an
  `action_id`, which is a SHA-256 hash of the canonical action payload (spec 05).

## Endpoints

| Method | Path | Phase | Description |
|---|---|---|---|
| GET | `/health` | 0 | Liveness. Never touches dependencies. |
| GET | `/health/ready` | 0 | Readiness: checks Qdrant (Phase 0), plus the MCP server and checkpointer (Phase 2). `503` if any is down. |
| POST | `/chat` | 1 | Send a message; runs the graph until it completes or pauses. |
| GET | `/runs/{run_id}` | 2 | Current state of a run (status, answer, pending action). |
| POST | `/runs/{run_id}/approve` | 2 | Approve the pending action and resume. |
| POST | `/runs/{run_id}/reject` | 2 | Reject the pending action and resume (the agent reports it did nothing). |

`/chat` is synchronous request/response (it returns when the run completes or pauses).
The LLM timeout bounds it (spec 07); the endpoint has an overall deadline of 60 s and then
returns `504` with the run marked `failed`.

## Data models

```python
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: UUID | None = None          # omit to start a new conversation

class Citation(BaseModel):
    source: str                             # repo-relative path, e.g. "docs/authentication.md"
    section: str                            # heading path, e.g. "Authentication > API keys"
    chunk_id: str
    quote: str | None = None                # short supporting excerpt (<= 300 chars)

class PendingAction(BaseModel):
    action_id: str                          # sha256 of the canonical tool call payload
    tool: Literal["create_github_issue"]
    arguments: CreateIssueInput             # spec 03
    rationale: str                          # why the agent wants to do this

class RunStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_APPROVAL = "awaiting_approval"
    REFUSED = "refused"
    FAILED = "failed"

class RunResponse(BaseModel):
    run_id: UUID
    thread_id: UUID
    status: RunStatus
    answer: str | None = None
    citations: list[Citation] = []
    pending_action: PendingAction | None = None
    action_result: ActionResult | None = None   # e.g. created issue URL, or dry-run payload
    refusal_reason: str | None = None

class ApproveRequest(BaseModel):
    action_id: str                          # must match the pending action (prevents approving a stale or changed action)
    comment: str | None = Field(default=None, max_length=500)

class RejectRequest(BaseModel):
    action_id: str
    reason: str | None = Field(default=None, max_length=500)

class ErrorResponse(BaseModel):
    error: str                              # machine-readable code, e.g. "run_not_found"
    message: str
    request_id: str
```

`POST /chat` and both decision endpoints return `RunResponse`.

## Status codes

| Situation | Code | `error` |
|---|---|---|
| Validation failure (Pydantic) | 422 | `validation_error` |
| Unknown `run_id` | 404 | `run_not_found` |
| Approve/reject when the run is not awaiting approval | 409 | `run_not_awaiting_approval` |
| `action_id` does not match the pending action | 409 | `action_mismatch` |
| Missing/invalid API key (when enabled) | 401 | `unauthorized` |
| Dependency failure (LLM, MCP, Qdrant) | 502 | `upstream_error` |
| Run deadline exceeded | 504 | `run_timeout` |

A refusal is **not** an error: it is `200` with `status="refused"`.

## Cross-cutting

- **Auth**: if `API_KEY` is set, every endpoint except `/health*` requires `X-API-Key`
  (compared in constant time). Required when `ENVIRONMENT=aws` (startup fails otherwise).
- **Request ID**: middleware accepts or generates `X-Request-ID`, binds it to logs and traces,
  and echoes it in the response.
- **Concurrency**: decisions on the same run are serialized (per-run `asyncio.Lock`), so a
  double click on approve executes the action at most once; the second call gets `409`.
- **Lifespan**: the app startup opens the checkpointer, the MCP client session and the LLM
  client; shutdown closes them. Dependencies are injected with `Depends`, so tests swap them.

## Acceptance criteria

- Phase 0: `/health` → `200 {"status":"ok","version":...}`; `/health/ready` → `200`/`503` depending on Qdrant. ✅ tested
- Phase 1: `POST /chat` with an in-scope question returns `completed` with at least one citation
  whose `source` exists in `docs/`; an out-of-scope question returns `refused`.
- Phase 2: an action request returns `awaiting_approval` with a `pending_action`; `approve` with the
  right `action_id` returns `completed` with `action_result`; a wrong `action_id` returns `409`;
  approving twice returns `409` on the second call; `reject` returns `completed` and no tool call is made.
- OpenAPI at `/docs` documents every model above.
