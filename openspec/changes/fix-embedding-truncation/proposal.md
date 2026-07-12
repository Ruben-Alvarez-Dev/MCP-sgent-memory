# Change: fix-embedding-truncation

- **Status**: proposed (awaiting Rubén's approval) — planning only, no code yet
- **Owner**: database · **Release**: v2.2.0 (Phase 2, P0 bugfix batch)

## Why

Two independent P0 data-corruption bugs live in the embedding path, found in the 2026-07-12 database audit (`docs/plan/IMPROVEMENT-PLAN.md` §2.1):

- **P0-2**: `shared/embedding.py` computes `cache_key = text if len(text) <= 200 else text[:200]` and then feeds that *same truncated string* into the LRU-cached embed call — the truncated 200-char prefix is what actually gets sent to the backend, not the full (already-capped-at-2000-char) text. Because `_get_default_backend()`'s wrapper always returns a truthy tuple on the in-memory path, `get_embedding()` returns immediately after that call — the SQLite persistent-cache read/write path below it (lines 536-547 in the current file) is unreachable dead code. Every memory whose text is longer than 200 chars is embedded on its first 200 chars only, and the resulting degraded vector is written into the persistent cache keyed by the *full* text's hash — poisoning it permanently.
- **P0-3**: `shared/embedding_cache.py` keys persistent cache rows by `sha256(text)` alone — no model, no dimension. Swapping `EMBEDDING_BACKEND`/`EMBEDDING_MODEL` (already an active axis: `adaptive-model-tier` role→model matrix, `model-stack-2026` swap) silently serves stale vectors from a different model/dimension, no eviction exists, and the table grows unbounded.

Both bugs violate `openspec/AGENTS.md` §1 (no silent degradation — degradation must log loudly) and directly cause the unsearchable/corrupt-memory failure mode this project's data layer exists to prevent.

## What

1. **Full-text embedding path** (`shared/embedding.py`): decouple the in-memory LRU cache key from the text actually sent to the backend — the backend must always receive the full (smart-truncated-to-2000-char) text, never a further 200-char prefix. The pre-existing 2000-char safety cap (tokenizer/context-window guard) is kept, but truncation events become a loud `WARNING` log (original vs. truncated length) instead of silent — closing the "no silent truncation" gap for genuinely oversized text.
2. **Model/dimension-aware cache key** (`shared/embedding_cache.py`): add a `model_id` concept to `EmbeddingBackend` (one property per backend: `LlamaCppBackend` → resolved gguf path, `HttpBackend`/`LlamaServerBackend` → configured model name, `NoOpBackend` → class name fallback) and fold `model_id` + `dim` into the cache key (`sha256(model_id \x1f dim \x1f text)`), plus explicit `model`/`dim` columns for introspection and targeted purges — not just baked into the opaque hash.
3. **Eviction policy**: bounded row count (`EMBEDDING_CACHE_MAX_ROWS`, default 50 000) enforced by LRU-by-`last_accessed_at` pruning inside `cache_set`, so the SQLite file no longer grows unbounded.
4. **One-shot purge script** (`bin/purge_embedding_cache.py`): backs up `embedding_cache.db` before mutating, then wipes the *entire* cache table. Whole-cache purge (not selective) is the only defensible option: the current schema stores only a hash, not the original text length, so there is no way to tell after the fact which rows were poisoned by P0-2 versus computed correctly on short text. `--dry-run` supported; idempotent.

## Impact

- Touches: `src/shared/embedding.py` (backend ABC gains `model_id`; `get_embedding` full-text path + loud-truncation log), `src/shared/embedding_cache.py` (key format, schema migration, eviction), new `bin/purge_embedding_cache.py`, new `tests/core/test_embedding.py` + `tests/core/test_embedding_cache.py` (currently zero coverage on either file — confirmed via `find tests -iname "*embedding*"` → no matches).
- Non-goals: wiring `shared/model_tier.py` role→model resolution into `embedding.py` (tracked as the still-open item 6 of `adaptive-model-tier`, separate concern); a formal `PRAGMA user_version` migration framework (tracked separately as the `sqlite-migrations` change — this change uses a minimal, guarded, idempotent `ALTER TABLE ... ADD COLUMN` migration scoped to `embedding_cache.db` only, consistent with the ad-hoc-migration pattern already present elsewhere in this codebase).
- Spec delta: `openspec/changes/fix-embedding-truncation/specs/embedding-pipeline/spec.md`. No `openspec/specs/embedding-pipeline/` baseline exists yet (only `model-stack` and the in-progress `l0-capture` baseline are present under `openspec/specs/` as of this writing) — this delta is written as a **self-contained target end-state description**, per the task instructions, and must be reconciled against the Phase 1 baseline spec once `embedding-pipeline` lands there.

## Acceptance

- Unit test proves a >200-char text reaches `backend.embed()` unmodified (full text, not a 200-char prefix) on both cache-miss and cache-hit paths.
- Unit test proves two different `(model_id, dim)` pairs for identical text produce different cache keys and independent hits/misses (no stale cross-model serve).
- Unit test proves `cache_set` enforces `EMBEDDING_CACHE_MAX_ROWS` by evicting least-recently-accessed rows.
- `bin/purge_embedding_cache.py --dry-run` reports without mutating; without `--dry-run` it backs up then empties the table; both verified against a temp SQLite fixture, never a production DB, per `openspec/AGENTS.md` §1.
- Full `tests/core` green, `ruff check src tests` clean, before any commit closing an iteration.
