# 07 — LLM provider abstraction

Status: `accepted` · Phase: 1

## Goals

- One interface for "give me a model that returns this Pydantic type", with the provider chosen by
  config: **AWS Bedrock** (main) or **Ollama** (local development). No module outside
  `docs_assistant.llm` imports a provider SDK.
- Timeouts, bounded retries, and token/latency metadata on every call.

## Non-goals

- Routing between providers at runtime, or cost-based model cascades.

## Interface

```python
class LLMRole(StrEnum):
    AGENT = "agent"     # planner, answer, draft_issue
    JUDGE = "judge"     # eval LLM-as-judge (spec 09)

class StructuredLLM(Protocol):
    async def generate[T: BaseModel](
        self, schema: type[T], messages: Sequence[BaseMessage], *, run_name: str
    ) -> T: ...

def get_llm(role: LLMRole, settings: Settings) -> StructuredLLM: ...
```

`generate` wraps `chat_model.with_structured_output(schema, method="json_schema", include_raw=True)`:
- `json_schema` uses **native schema-constrained output** on both providers (Bedrock Converse
  `outputConfig`; Ollama `format=<schema>`). The `function_calling` method is avoided because it forces
  `tool_choice`, which current Claude models on Bedrock reject.
- On a parsing or validation failure, it retries once with the validation error appended (G6), and then
  raises `InvalidModelOutput`.
- Returns the parsed object; usage metadata (input and output tokens, latency) goes to the span and logs.

## Providers

| Provider | Class | Config | Notes |
|---|---|---|---|
| `bedrock` | `langchain_aws.ChatBedrockConverse` | `AWS_REGION` (default `us-east-1`), `BEDROCK_MODEL_ID` (agent), `JUDGE_MODEL_ID` | Credentials from the standard AWS chain (env, profile, ECS task role). botocore `Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3, "mode": "adaptive"})`. **No `temperature`**: current Claude models reject non-default sampling parameters. Determinism comes from the schemas and the prompts instead. |
| `ollama` | `langchain_ollama.ChatOllama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (default `qwen3:8b`), `OLLAMA_JUDGE_MODEL` | `temperature=0`; request timeout 60 s (local models are slower). Pull with `ollama pull qwen3:8b`. |
| `fake` | `FakeStructuredLLM` (tests only) | — | Returns queued Pydantic objects per `schema`; it records calls for assertions. Unit tests never hit a real LLM. |

**Model IDs**: Bedrock IDs and cross-region inference-profile IDs are never hard-coded (decision D7).
`BEDROCK_MODEL_ID` defaults to empty, and startup fails with a clear message if `LLM_PROVIDER=bedrock`
and it is unset. The README shows how to list the available profiles:
`aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId,'anthropic')].inferenceProfileId"`.

## Error mapping

Provider exceptions (botocore `ClientError` throttling, timeouts, Ollama connection refused) map to
`LLMUnavailable` (→ API `502 upstream_error`); validation failures map to `InvalidModelOutput`.

## Acceptance criteria

- Unit: `get_llm` picks the provider from settings; bedrock without a model ID fails fast; the
  `json_schema` method is used (asserted on the bound runnable); one retry on invalid output and then an error.
- Integration (marked, opt-in): the same structured call round-trips on Ollama and, with credentials, on Bedrock.
