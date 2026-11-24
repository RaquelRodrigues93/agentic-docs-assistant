# 04 — RAG: ingestion and retrieval

Status: `accepted` · Phase: 1

## Goals

- Ingest `docs/**/*.md` into Qdrant as heading-aware chunks with enough metadata to cite
  **file and section**.
- Make ingestion idempotent: re-running it with unchanged docs changes nothing, and edited or deleted
  files are updated or removed.
- Keep retrieval quality measurable (spec 09: hit rate and MRR on the golden set).

## Non-goals

- Hybrid/sparse search and re-ranking in v1. The interface allows adding them later, and evals
  will show whether they are needed.
- Non-Markdown formats.

## Chunking

1. Parse Markdown into sections by heading (`#`–`###`). Each section keeps its **heading path**
   (`"Authentication > API keys > Rotating keys"`).
2. Sections longer than `CHUNK_MAX_TOKENS` (default 400, using the embedding tokenizer's count) are split on
   paragraph boundaries with `CHUNK_OVERLAP_TOKENS` (default 50). Fenced code blocks are never split.
3. The text that gets embedded is prefixed with its context: `"{doc title} > {heading path}\n\n{text}"`.
   This improves retrieval for short sections.
4. Front matter (`title`, optional `tags`) is used when present; otherwise the title is the first H1.

## Data model

```python
class Chunk(BaseModel):
    chunk_id: str        # uuid5(NAMESPACE, f"{source}#{heading_path}#{index}"): deterministic
    source: str          # repo-relative path
    section: str         # heading path
    anchor: str          # GitHub-style slug of the deepest heading, for links
    text: str            # original text (without the context prefix)
    content_hash: str    # sha256(text): used to skip unchanged chunks
    doc_title: str
```

Qdrant collection `docs` (name configurable): one dense vector of size 384, cosine distance
(`BAAI/bge-small-en-v1.5`); the payload holds every `Chunk` field, with a payload index on `source`.

## Ingestion CLI

`uv run docs-assistant-ingest [--docs-dir docs] [--recreate]`

- Creates the collection if it does not exist. With `--recreate`, it drops it first, and it fails
  if the existing vector size differs from the configured model's.
- Upserts new or changed chunks (compared by `chunk_id` and `content_hash`), and deletes points whose
  `source` no longer exists or whose `chunk_id` is no longer produced.
- Prints a summary (`added / updated / deleted / unchanged`) and exits non-zero on error.
- Runs as a one-off compose service (`ingest`) and as the ECS container's startup step (spec 10).

## Retrieval (`docs_assistant.rag.retriever`)

```python
class Retriever(Protocol):
    async def search(self, query: str, top_k: int = 6) -> list[RetrievedChunk]: ...
```

- Uses `AsyncQdrantClient` with a 5 s timeout. The query is embedded with the same model and prefix
  convention (`"query: "` handling according to the model card).
- `score_threshold` (default 0.3, tuned on evals) filters weak matches. Returning no chunks is a
  valid result, and the answer node then says the docs do not cover the question.
- At most 2 chunks per `source` + `section`, to avoid redundancy.

## Embeddings abstraction (`docs_assistant.rag.embeddings`)

```python
class Embedder(Protocol):
    dimension: int
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

- `FastEmbedEmbedder` (default; runs in a thread pool because fastembed is synchronous).
- `BedrockEmbedder` (`amazon.titan-embed-text-v2`, optional, `EMBEDDINGS_PROVIDER=bedrock`).
  Changing the provider requires `--recreate`, which the dimension check enforces.

## Acceptance criteria

- Unit: chunker keeps heading paths, never splits code fences, produces deterministic IDs; re-ingest of
  unchanged docs reports `0 added / 0 updated / 0 deleted` (Qdrant in-memory mode `QdrantClient(":memory:")`).
- Unit: citations map to real files and sections in `docs/`.
- Eval (spec 09): retrieval hit@6 ≥ 0.85 and MRR ≥ 0.6 on the golden set (thresholds revisited after the first baseline).
