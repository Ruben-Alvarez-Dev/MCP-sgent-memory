# Spec — embedding-pipeline

Status: current | Last-verified: 2026-07-12

> Source: `shared/embedding.py` (695 lines), `shared/embedding_cache.py`, `shared/qdrant_client.py`. Consumed by every layer that writes to Qdrant (`l0-capture`, `l2-conversations`, `l3-facts`, and the not-yet-covered `l0-to-l4-consolidation`, `l3-decisions`).

## Capability: text → vector, with two-tier caching

### Backends (`EmbeddingBackend` ABC, selected by `EMBEDDING_BACKEND` env or availability probe)

`LlamaCppBackend` (bundled binary, subprocess) · `LlamaServerBackend` (HTTP to a running `llama-server`) · `HttpBackend` (generic HTTP) · `NoOpBackend`. Default resolution when `EMBEDDING_BACKEND` is unset: try `LlamaServerBackend.is_available()`, else fall back to `LlamaCppBackend`. Dim = `EMBEDDING_DIM` env, default 1024 (BGE-M3-compatible; ADR-0006 targets migrating the default model to Qwen3-Embedding-0.6B at the same dim, no Qdrant migration needed).

### Public API

`get_embedding(text)` (sync, cached) · `get_embeddings(texts)` (sync, uncached loop) · `async_embed(text)` / `async_embed_batch(texts)` (thread-pool wrappers) · `safe_embed(text)` (never raises).

### Caching

1. In-memory `lru_cache` (`EMBEDDING_CACHE_SIZE`, default 512), keyed by `cache_key`.
2. Persistent SQLite cache (`embedding_cache.db`), keyed by `sha256(text)`.

### Known defects (all confirmed present by direct source read, 2026-07-12 — matches `docs/plan/IMPROVEMENT-PLAN.md` §2.1 P0-2/P0-3/P0-4)

- **P0-2 — truncation, still live**: `get_embedding()` line 524 sets `cache_key = text if len(text) <= 200 else text[:200]`, then passes `cache_key` (not `text`) into the `lru_cache`-wrapped `_cached_embed()`. For any text longer than 200 characters, **only the first 200 characters are ever embedded** — the vector persisted for the whole document represents its opening sentence(s) only. The full-text embedding path is unreachable through this call for long texts (the persistent SQLite cache is still keyed/populated by full `text`, so `cache_get(text)`/`cache_set(text, vec)` store the *truncated* vector under the full-text key — compounding the corruption into the persistent layer too).
- **P0-3 — cache key has no model/dimension namespace**: `embedding_cache.py` keys rows by `sha256(text)` only (`cache_get`/`cache_set`). Changing `EMBEDDING_MODEL` or `EMBEDDING_DIM` (e.g. the planned Qwen3-Embedding-0.6B migration) will silently serve stale vectors from the previous model for any text seen before — no invalidation, no eviction, no model tag in the schema.
- **P0-4 — zero-vectors persisted as valid**: `safe_embed()` (line ~600-616) returns `[0.0] * dim` on any embedding failure, after logging a warning. Every caller (`_store_memory` in l0-capture, `add_memory` in l3-facts, `save_conversation` in l2-conversations) upserts this zero-vector to Qdrant unconditionally — it passes `qdrant.upsert()`'s only check (`len(vector) == embedding_dim`), producing a permanently unsearchable but structurally valid memory record with no flag distinguishing it from a real one.
- **Qdrant write integrity gap (P0-6, boundary with this pipeline)**: `qdrant_client.py::upsert`/`upsert_batch` (lines 198-232) call `client.put(...)` inside `_retry(_do)` but never call `resp.raise_for_status()` or check `resp.status_code` — an HTTP 4xx/5xx from Qdrant (including a dimension mismatch on an existing collection) is silently swallowed and treated as success by every caller in this list. Contrast with `set_payload` (line 254), which does call `raise_for_status()` — the check exists in the codebase but was not applied consistently to `upsert`/`upsert_batch`.

### Test coverage

No dedicated tests found for the truncation/zero-vector/cache-key-collision failure modes above (P1: "embedding fallback 0 tests").
