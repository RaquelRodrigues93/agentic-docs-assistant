# 05 — Human-in-the-loop approvals

Status: `accepted` · Phase: 2

## Goals

- No external side effect without an explicit human decision tied to the **exact** action shown.
- Paused runs survive process restarts.
- Decisions are auditable (who, when, what, outcome).

## Non-goals

- Editing the drafted action during approval (v1: approve or reject only; to change it, reject and
  ask again). Multi-approver workflows.

## Mechanism

1. `draft_action` produces an `IssueDraft`. The graph builds a `PendingAction`:
   - `arguments`: the `CreateIssueInput` that **will** be sent, without the idempotency key.
   - `action_id = sha256(canonical_json({"tool": tool, "arguments": arguments}))`, where
     canonical JSON means sorted keys, no whitespace, and UTF-8.
2. `await_approval` calls `interrupt(pending_action.model_dump())`. The graph pauses, the checkpoint
   is saved, and the API returns `status="awaiting_approval"` with the `pending_action`.
3. The client calls `POST /runs/{run_id}/approve {action_id}` or `/reject {action_id, reason}`.
   The API checks that the run is awaiting approval and that `action_id` matches the checkpointed
   pending action, and then resumes with `Command(resume=ApprovalDecision(...).model_dump())`.
4. `await_approval` re-runs, receives the decision from `interrupt()`, and stores it in state. It has
   **no side effects**, so the re-run is safe.
5. If the action was approved, `execute_action` calls `create_github_issue` with the checkpointed
   arguments and `idempotency_key=action_id`. **It never uses LLM output generated after approval.**
   If it was rejected, `respond` produces "OK, I did not open the issue" and no tool is called.

```python
class ApprovalDecision(BaseModel):
    approved: bool
    action_id: str
    comment: str | None = None
    decided_at: datetime

class ActionResult(BaseModel):
    tool: str
    dry_run: bool
    url: str | None
    summary: str
```

## Safety properties (tested)

| Property | How |
|---|---|
| Nothing external runs without approval | `execute_action` is reachable only from `await_approval` with `approved=True`. A test asserts the MCP mock received zero `create_github_issue` calls on the pending, rejected and expired paths. |
| You approve what you saw | `action_id` binds the approval to the exact payload; a mismatch gets `409`. |
| No double execution | A per-run lock plus the status check (the second decision gets `409`) plus the idempotency key on the MCP side. |
| Restart-safe | The pending state lives in the checkpointer; a new process resumes it (test with a fresh graph and the same SQLite file). |
| Approvals expire | Pending actions older than `APPROVAL_TTL_MINUTES` (default 60) are auto-rejected on access, with status `failed: approval_expired`. |

## Audit

Every decision is logged as a structured event `approval.decided` with `run_id`, `thread_id`,
`action_id`, `approved`, `comment`, the outcome URL or error, and `request_id`. It is also a span attribute
in the trace (spec 08).

## Acceptance criteria

- Phase 2 criteria in spec 01, plus the table above as automated tests.
- A demo script (`scripts/demo_hitl.sh`) runs the full brief flow against the local stack:
  ask → answer with citations → request issue → approve → link (dry-run by default).
