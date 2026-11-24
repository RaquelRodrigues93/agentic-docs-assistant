# Specs

Specs are written before code (spec-driven development). Each spec has **goals**,
**non-goals**, **interfaces**, **data models**, and **acceptance criteria**. A change
that alters an interface or an acceptance criterion updates the spec in the same PR.

| # | Spec | Phase |
|---|---|---|
| 00 | [Overview and architecture](00-overview.md) (includes the decision log) | 0 |
| 01 | [HTTP API](01-api.md) | 0–2 |
| 02 | [Agent graph](02-agent-graph.md) | 1–2 |
| 03 | [MCP server](03-mcp-server.md) | 2 |
| 04 | [RAG: ingestion and retrieval](04-rag.md) | 1 |
| 05 | [Human-in-the-loop approvals](05-hitl.md) | 2 |
| 06 | [Guardrails](06-guardrails.md) | 2 |
| 07 | [LLM provider abstraction](07-llm-providers.md) | 1 |
| 08 | [Observability](08-observability.md) | 3 |
| 09 | [Evals](09-evals.md) | 3 |
| 10 | [Infrastructure (AWS)](10-infra.md) | 4 |

Status values used in each spec header: `draft` → `accepted` → `implemented`.
