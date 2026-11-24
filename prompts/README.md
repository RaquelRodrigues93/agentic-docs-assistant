# Prompts

Prompts are versioned files, reviewed like code and measured by evals (spec 09).

```
prompts/<name>/v<N>.md
```

Each file has YAML front matter followed by the template body:

```markdown
---
name: answer
version: 1
description: Grounded answer with citations to retrieved chunks.
inputs: [question, documents]
---
You are ... {question} ... {documents}
```

Rules:
- A released version is **immutable**. To change a prompt, add `v<N+1>.md` and bump `ACTIVE_PROMPTS`
  in `docs_assistant.agent.prompts`.
- Placeholders are filled from a typed model; a missing input raises.
- Retrieved text goes in a delimited `<documents>` block and is described as data, not instructions.

Planned prompts: `planner` (Phase 1), `answer` (Phase 1), `draft_issue` (Phase 2), `judge` (Phase 3).
