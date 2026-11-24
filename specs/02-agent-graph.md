# 02 — Agent graph (LangGraph)

Status: `accepted` · Phases: 1 (answer path), 2 (action path, MCP, HITL)

## Goals

- A stateful, multi-step graph: **guard → plan → retrieve → answer**, plus an **act** path
  (draft → approve → execute) and a **refuse** path.
- Every LLM call returns a Pydantic model (structured output). The graph never parses free text.
- Every run is checkpointed, so a run paused for approval survives an API restart.
- Bounded: a step budget per run and a recursion limit.

## Non-goals

- Autonomous multi-action loops. One run performs at most **one** external action.
- Sub-agents or parallel branches (not needed; adds tracing noise).

## Graph

```mermaid
flowchart TD
    START((start)) --> guard[guard_input]
    guard -->|invalid| refuse
    guard --> plan
    plan -->|answer| retrieve
    plan -->|action| retrieve_ctx[retrieve]
    plan -->|out_of_scope| refuse
    plan -->|clarify| respond
    retrieve --> answer --> respond
    retrieve_ctx --> draft[draft_action]
    draft --> approval[await_approval<br/><i>interrupt()</i>]
    approval -->|approved| execute[execute_action]
    approval -->|rejected| respond
    execute --> respond
    refuse --> END((end))
    respond --> END
```

In code, `retrieve` is a single node: the `plan` router sends both paths to it, and a
conditional edge after it reads `state.decision.kind`.

| Node | Does | LLM | Tools (via MCP) |
|---|---|---|---|
| `guard_input` | Input validation (spec 06). Sets `refusal` on failure. | no | — |
| `plan` | Classifies the request and picks the next step → `PlannerDecision`. | yes | — |
| `retrieve` | Calls `search_docs` with the planner's query (top-k = 6). | no | `search_docs` |
| `answer` | Grounded answer with citations → `GroundedAnswer`. | yes | — |
| `draft_action` | Drafts the issue from the request and retrieved context → `IssueDraft`. | yes | — |
| `await_approval` | `interrupt(PendingAction)`; resumes with `ApprovalDecision`. Has no side effects. | no | — |
| `execute_action` | Calls `create_github_issue` with the **approved** arguments. | no | `create_github_issue` |
| `refuse` | Builds the refusal message. | no | — |
| `respond` | Assembles the final `RunResponse` fields in state. | no | — |

**Why `await_approval` and `execute_action` are separate nodes:** on resume, LangGraph
re-runs the interrupted node from its start. If the side effect lived in the same node as
`interrupt()`, a retry could repeat it. Here the side effect is in a node that runs exactly
once after the decision, and the tool call carries an idempotency key (spec 03).

## State

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]   # conversation (thread-scoped)
    run_id: str
    steps: int                                  # incremented by every node; guarded by MAX_STEPS
    decision: PlannerDecision | None
    retrieved: list[RetrievedChunk]             # from search_docs (spec 04)
    answer: GroundedAnswer | None
    pending_action: PendingAction | None
    approval: ApprovalDecision | None
    action_result: ActionResult | None
    refusal: Refusal | None
    error: str | None
```

## Structured outputs

```python
class AnswerStep(BaseModel):
    kind: Literal["answer"] = "answer"
    search_query: str = Field(max_length=300)    # rewritten for retrieval, standalone (resolves "it", "that")

class ActionStep(BaseModel):
    kind: Literal["action"] = "action"
    tool: Literal["create_github_issue"]
    search_query: str                            # to ground the issue in the docs
    intent_summary: str

class OutOfScopeStep(BaseModel):
    kind: Literal["out_of_scope"] = "out_of_scope"
    reason: str

class ClarifyStep(BaseModel):
    kind: Literal["clarify"] = "clarify"
    question: str

class PlannerDecision(BaseModel):
    step: Annotated[AnswerStep | ActionStep | OutOfScopeStep | ClarifyStep, Field(discriminator="kind")]

class GroundedAnswer(BaseModel):
    answer: str
    citations: list[CitationRef] = Field(min_length=0)   # refer to retrieved chunk_ids
    is_answerable: bool                           # False → "the docs don't cover this" (and suggest opening an issue)

class CitationRef(BaseModel):
    chunk_id: str
    quote: str | None = Field(default=None, max_length=300)

class IssueDraft(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    body: str = Field(min_length=20, max_length=5000)
    labels: list[Literal["documentation", "bug", "enhancement"]] = ["documentation"]
    rationale: str
```

**Citations are validated in code, not trusted.** Each `CitationRef.chunk_id` must exist in
`state.retrieved`. Unknown IDs are dropped and logged. If an answerable answer ends up
with no valid citation, it is downgraded to `is_answerable=False`. `source` and `section`
are copied from the retrieved chunk, never from the LLM.

## Prompts

- Stored as `prompts/<name>/v<N>.md` with YAML front matter (`name`, `version`, `description`,
  `inputs`). The body is a template with named placeholders filled by `str.format_map` from a typed
  model, so a missing input fails loudly.
- Prompts: `planner`, `answer`, `draft_issue`. The active versions are pinned in
  `docs_assistant.agent.prompts.ACTIVE_PROMPTS`. Changing a prompt means adding a new file
  (`v2.md`), never editing a released version. Evals report the prompt versions they ran with.
- Retrieved text goes in a delimited `<documents>` block, and the system prompt says to treat it
  as data, not instructions (spec 06).

## Limits

- `MAX_STEPS = 10` node executions per run (state counter, checked by every node via a decorator);
  exceeding it ends the run with `failed: step_budget_exceeded`.
- LangGraph `recursion_limit = 15` as a backstop.
- At most 1 `search_docs` call per run in Phase 1/2 (one retrieval pass; spec 06 allowlist enforces tools).

## Checkpointing

- `AsyncSqliteSaver` (path from `CHECKPOINT_DB_PATH`, default `./data/checkpoints.sqlite`),
  opened in the API lifespan. Postgres (`langgraph-checkpoint-postgres`) through `CHECKPOINTER=postgres`.
- `thread_id` = conversation. The run registry (`run_id → thread_id, status, created_at`) is a small
  table in the same SQLite file, managed by `docs_assistant.agent.runs`.

## Acceptance criteria

- Unit tests with a fake LLM (returns preset Pydantic objects) and the in-process MCP server cover:
  answer path, out-of-scope refusal, clarify, action → interrupt, approve → executed once,
  reject → not executed, step budget exceeded, hallucinated citation dropped.
- A run interrupted for approval can be resumed by a **new** graph instance that uses the same
  checkpointer (simulated restart).
- The graph is exported as a Mermaid diagram (`graph.get_graph().draw_mermaid()`), and a test fails if the committed diagram is out of date.
