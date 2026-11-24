# 08 — Observability

Status: `accepted` · Phase: 3 (structured logs from Phase 0)

## Goals

- Trace every agent run end to end (graph nodes, LLM calls with prompts, tokens and latency, MCP
  tool calls, retrieval results) in **Arize Phoenix** running locally.
- LangSmith as an alternative, selected by config. Tracing can be turned off.
- Correlate traces, logs and API responses through `run_id` and `request_id`.

## Design

- `TRACING_BACKEND = phoenix | langsmith | none` (default `phoenix` locally, `none` in CI unit tests).
- **Phoenix**: `phoenix.otel.register(project_name="agentic-docs-assistant", endpoint=PHOENIX_COLLECTOR_ENDPOINT, batch=True)`
  plus `openinference-instrumentation-langchain` (`LangChainInstrumentor().instrument(tracer_provider=...)`),
  which captures LangGraph nodes and LLM calls. MCP tool calls get manual spans
  (`mcp.call_tool`, attributes `tool.name`, `tool.dry_run`, and sizes only, no full payloads in live mode).
- **LangSmith**: set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`; LangChain traces
  natively. Our manual spans are skipped in that mode.
- Set up once in the app lifespan (`docs_assistant.observability.setup_tracing(settings)`), with an
  idempotent guard. Failure to reach the collector **never** fails a request (the batch exporter drops data).
- Root span per run, `agent.run`, with attributes `run_id`, `thread_id`, `request_id`, `prompt_versions`,
  `llm.provider`, `outcome` (completed, refused, awaiting_approval, failed), and `refusal.code` / `guardrail.tripped`.
- Logs: structlog JSON with `run_id` and `request_id` bound through contextvars; secrets redacted (G8).

## Evals ↔ traces

Eval runs use the project name `agentic-docs-assistant-evals`, so their traces stay separate from interactive runs.
Each eval case is tagged with `eval.case_id`.

## AWS

Phoenix is not deployed to AWS by default (it would cost more than the app). In `aws`,
`TRACING_BACKEND` is `none` or `langsmith`; CloudWatch Logs gets the JSON logs (spec 10).

## Acceptance criteria

- With the compose stack running, one `/chat` request produces a trace in Phoenix (`localhost:6006`)
  with nested spans: `agent.run` → nodes → LLM call(s) and the `mcp.call_tool` span.
- `TRACING_BACKEND=none` does no OTel setup (tested). Tracing errors don't propagate (tested with an unreachable endpoint).
