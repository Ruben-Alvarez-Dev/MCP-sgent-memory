# Tasks — fix-embedding-truncation

Numbered iterations map 1:1 to `openspec/AGENTS.md` §4 (`I01, I02, …`). Each is independently red→green TDD-able; evidence goes to `evidence/I<NN>.md` when implemented. None are started — this change is planning-only.

- [ ] 1. Full-text embed path: remove the 200-char `cache_key` truncation in `get_embedding()`; the in-memory `lru_cache` (`_cached_embed`) must receive and embed the same (≤2000-char, safety-capped) text in both the cache-miss and cache-hit branches.
      Target: `src/shared/embedding.py:513-549` (`get_embedding`), `:500-506` (`_cached_embed` closure).
      Test: `tests/core/test_embedding.py` — stub backend records `embed()` call args; assert a >200-char, ≤2000-char input string reaches `embed()` byte-for-byte unmodified. Red: fails against current code (arg truncated to 200 chars). Green: after the fix.

- [ ] 2. Loud truncation logging at the pre-existing 2000-char safety cap (`smart_truncate`).
      Target: `src/shared/embedding.py:518-521` (the `if len(text) > 2000` block).
      Test: same file — `caplog` asserts exactly one `WARNING` record (with original/truncated lengths in the message) when input >2000 chars, and zero such records when input ≤2000 chars.

- [ ] 3. `EmbeddingBackend.model_id` property (ABC + one override per concrete backend per design.md §2.3); `LlamaServerBackend` gains a stored `self._model` (env-driven, replaces the hardcoded `"BGE-M3"`/`"bge-m3"` literals in `embed`/`embed_batch`).
      Target: `src/shared/embedding.py` — `EmbeddingBackend` ABC (~:55-71), `LlamaCppBackend` (~:176-236), `HttpBackend` (~:297-349), `LlamaServerBackend` (~:366-434), `NoOpBackend` (~:354-361).
      Test: `tests/core/test_embedding.py` — one assertion per backend class, constructed with fixed env/paths (no subprocess/network), matching the table in design.md §2.3.

- [ ] 4. Model+dimension-aware persistent cache key (`sha256(model_id \x1f dim \x1f text)`); `cache_get`/`cache_set` signatures gain `model_id: str, dim: int` parameters; callers in `embedding.py` updated to pass `backend.model_id, backend.dim`.
      Target: `src/shared/embedding_cache.py:42-76` (`cache_get`, `cache_set`), `src/shared/embedding.py:524-547` (call sites).
      Test: `tests/core/test_embedding_cache.py` — same text, two different `(model_id, dim)` pairs → distinct keys, independent hit/miss (a set under pair A is a miss under pair B).

- [ ] 5. Schema migration: `model TEXT NOT NULL DEFAULT ''`, `dim INTEGER NOT NULL DEFAULT 0`, `last_accessed_at REAL DEFAULT (strftime('%s','now'))` columns + index, via guarded idempotent `_migrate_schema()` (design.md §2.5); `cache_get` updates `last_accessed_at` on hit.
      Target: `src/shared/embedding_cache.py` (`_init_db`, new `_migrate_schema`, `cache_get`).
      Test: `tests/core/test_embedding_cache.py` — running `_migrate_schema` twice on the same connection is a no-op (no error, columns present exactly once via `PRAGMA table_info`); a hit updates `last_accessed_at` (monotonic increase, `time.sleep`-free via injectable clock or two sequential hits compared).

- [ ] 6. Eviction: `EMBEDDING_CACHE_MAX_ROWS` (default 50000) enforced in `cache_set` via LRU-by-`last_accessed_at` pruning (design.md §2.7).
      Target: `src/shared/embedding_cache.py` (`cache_set`).
      Test: `tests/core/test_embedding_cache.py` — seed cap+k rows with distinct `last_accessed_at`, trigger one more `cache_set`, assert row count == cap and the k oldest-accessed rows are gone, newest retained.

- [ ] 7. One-shot purge script `bin/purge_embedding_cache.py`: backs up `embedding_cache.db` (timestamped copy) before mutating, reports pre/post row counts, `--dry-run` flag (no mutation, no backup), idempotent (safe to re-run on an already-empty cache).
      Target: new `bin/purge_embedding_cache.py`.
      Test: `tests/core/test_purge_embedding_cache.py` — import the script's main function directly against a temp DB fixture (never `~/.memory` or any real path); `--dry-run` leaves row count and file untouched; real run produces a backup file with the pre-purge row count and leaves the live table empty; second real run on the now-empty cache is a no-op (still succeeds, backup of 0 rows).

- [ ] 8. Integration test tying I01-I06 together end-to-end (P0-2 + P0-3 acceptance criteria from `proposal.md`).
      Target: `tests/core/test_embedding.py` (new integration-style test class) using a stub backend + a real temp-path SQLite persistent cache (no `~/.memory`, no network).
      Test: full text (not 200-char prefix) reaches the stub backend on cache miss; persistent-cache round-trip is correctly keyed by `(model_id, dim, text)`; swapping the stub's `model_id` between two calls with identical text causes a second miss + recompute (no stale cross-model serve) — directly exercises the acceptance bullets in `proposal.md`.

Iteration ordering: 1→2 (same file, sequential to avoid rebasing the same lines twice), 3 is independent and can run before or after 1-2, 4 depends on 3 (`model_id`), 5 must land before 6 (schema before eviction logic that reads `last_accessed_at`), 7 depends on 4-5 (correct schema/key format to purge against), 8 depends on all of 1-7.
