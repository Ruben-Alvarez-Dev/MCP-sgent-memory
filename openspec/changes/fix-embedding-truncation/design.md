# Design — fix-embedding-truncation

## 1. Root cause (dual-validated)

**P0-2.** Read of the current file (source 1) plus trace of the call path (source 2 — reasoning through execution, no test harness exists yet for this file):

```python
# src/shared/embedding.py:513-549 (get_embedding), current state
if len(text) > 2000:
    text = smart_truncate(text, 2000)          # (A) safety cap — intentional, kept

cache_key = text if len(text) <= 200 else text[:200]   # (B) the bug
if _backend_cache_fn is not None:
    result = _backend_cache_fn(cache_key)       # (C) cache_key is passed AS THE TEXT TO EMBED
    if result and isinstance(result, tuple):
        vec = list(result)
        cache_set(text, vec)                     # (D) but persisted under the FULL text's hash
        return vec                                # (E) always returns here — (F)/(G) below unreachable

cached = cache_get(text)                          # (F) dead code
...
vec = _default_backend.embed(text)                # (G) dead code — the "real" full-text embed call
```

`_cached_embed` (the function wrapped by `functools.lru_cache` at module init, `:500-506`) takes its single argument and passes it straight to `backend.embed(text)`. Since (C) calls it with `cache_key` — truncated to 200 chars for anything longer — `backend.embed()` never sees more than 200 chars of any text that started out longer than that. (D) then writes that degraded vector into the *persistent* cache keyed by `sha256(full_text)`, so the poison survives process restarts. Steps (F)/(G), which look like the "real" full-text path, are unreachable because (E) returns unconditionally once the in-memory branch produces any tuple (which it always does — `_cached_embed` either returns a cached tuple or computes and caches one).

**Why (B) exists at all**: almost certainly a copy of the *persistent*-cache convention (hash/short-key text for the dict key) applied by mistake to the *value* passed into the embed call, conflating "key used for the lru_cache dict" with "argument passed to the wrapped function" — in `functools.lru_cache` these are the same object, so truncating one truncates the other.

**P0-3.** `src/shared/embedding_cache.py:44,62` — `key = hashlib.sha256(text.encode()).hexdigest()`. No model or dimension enters the hash and no column stores them. Confirmed against `shared/config.py:35-39` (`embedding_backend: str = "llama_server"`, `embedding_model: str = ""`) — the active model is an axis that already changes today (env override) and is designed to change more (per `openspec/specs/model-stack/spec.md`, embedding role resolves to `qwen3-embedding:0.6b` once `adaptive-model-tier` item 6 wires `embedding.py` to `model_tier`). A cache keyed only by text cannot tell a 384-dim MiniLM vector from a 1024-dim BGE-M3 vector for the same string.

## 2. Decisions

### 2.1 Decouple LRU key from embed argument

The fix is to stop truncating the string that reaches `backend.embed()`. The in-memory `lru_cache` key becomes the same full (≤2000-char, post-safety-cap) text — Python dict-hashes a 2000-char string in single-digit microseconds; at `EMBEDDING_CACHE_SIZE=512` (default) worst case is ~1 MB of key storage, negligible. No separate truncated key is needed once the value truncation is removed, so `cache_key` is deleted outright rather than renamed — keeping a parallel "short key for dict lookups" would reintroduce exactly this bug class if anyone later reused it as the embed argument.

**Alternative considered**: hash the text for the lru_cache key and keep a side `dict[hash, str]` to recover the full text before calling `backend.embed()`. Rejected — adds a second piece of mutable global state to keep in sync with the lru_cache's own eviction, for a memory saving (a handful of KB) that doesn't matter at this scale. Simpler code with the same semantics wins.

### 2.2 Loud truncation at the 2000-char safety cap

`smart_truncate` (step A) is a deliberate, sentence-boundary-aware cap for tokenizer/context-window limits (documented in `shared/text.py:11-21`) — not part of the P0, and out of scope to remove (llama.cpp/Ollama context limits are a hardware fact, not a bug). What *is* in scope: AGENTS.md §1 requires every fallback/degradation to log loudly, and today this truncation is silent. Fix: log `WARNING` with original and truncated lengths whenever `len(text) > 2000`, so operators can see it happening (e.g. via `server.log` or a future metrics counter) instead of it being invisible.

### 2.3 `model_id` on `EmbeddingBackend`

Add an abstract-with-default `model_id: str` property to the `EmbeddingBackend` ABC:

| Backend | `model_id` |
|---|---|
| `LlamaCppBackend` | `str(self._model)` (resolved gguf path) or `"llama_cpp:unresolved"` if no model found |
| `HttpBackend` | `self._model` (already a string, defaults `"all-MiniLM-L6-v2"`) |
| `LlamaServerBackend` | `self._model` — **new** stored attribute, `os.getenv("EMBEDDING_MODEL") or "bge-m3"`; both `embed()` and `embed_batch()` are changed to send `self._model` instead of the current hardcoded, inconsistently-cased literals `"BGE-M3"` / `"bge-m3"` |
| `NoOpBackend` | default from the ABC (`self.__class__.__name__` → `"NoOpBackend"`) — test/fallback only, no real model to identify |

`LlamaServerBackend` is `Config.embedding_backend`'s actual default (`"llama_server"`), so without a real `model_id` there the P0-3 fix would be a no-op for the backend this system runs by default — the two-literal inconsistency (`"BGE-M3"` vs `"bge-m3"`) is fixed as a direct consequence of needing one canonical identifier, not a separate unscoped change.

**Non-goal**: consulting `shared/model_tier.py` for the model name. That wiring is explicitly tracked as the open item 6 of `adaptive-model-tier` (`docs/plan/IMPROVEMENT-PLAN.md` confirms it's unstarted: `grep -n "model_tier" src/shared/embedding.py` → no hits). Pulling it in here would couple two P0 changes and blow the "surgical, quirúrgico" scope; `model_id` here reflects whatever `EMBEDDING_BACKEND`/`EMBEDDING_MODEL` resolve to today, which is enough to stop cross-model cache poisoning.

### 2.4 Cache key format

```python
_SEP = "\x1f"  # ASCII unit separator — cannot appear in normal text, avoids field-injection collisions
key = hashlib.sha256(f"{model_id}{_SEP}{dim}{_SEP}{text}".encode("utf-8")).hexdigest()
```

Using a control-character separator (rather than e.g. `"|"`) rules out a text containing the literal separator sequence from colliding two different `(model_id, dim, text)` triples onto the same key — a low-probability but free-to-close risk given the fix is already touching this line.

### 2.5 Schema migration (ad-hoc, guarded, reversible)

No `PRAGMA user_version` framework exists in this codebase yet (tracked separately as `sqlite-migrations`, P1 finding in the audit — "no PRAGMA user_version, ad-hoc probe migration" is the *existing* pattern elsewhere in the code, not something this change invents). Scope here stays inside `embedding_cache.py` only:

```python
def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)")}
    if "model" not in cols:
        conn.execute("ALTER TABLE embeddings ADD COLUMN model TEXT NOT NULL DEFAULT ''")
    if "dim" not in cols:
        conn.execute("ALTER TABLE embeddings ADD COLUMN dim INTEGER NOT NULL DEFAULT 0")
    if "last_accessed_at" not in cols:
        conn.execute("ALTER TABLE embeddings ADD COLUMN last_accessed_at REAL DEFAULT (strftime('%s','now'))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_last_accessed ON embeddings(last_accessed_at)")
    conn.commit()
```

Called once at the top of `_init_db` and idempotently re-checked at the top of `cache_get`/`cache_set` (cheap `PRAGMA table_info` call, guards against a stale open connection from before the migration ran in-process). Existing rows get `model=''`, `dim=0` — these can never match a real `(model_id, dim)` lookup again (empty string / zero never equal a resolved backend's values), so they become inert rather than silently served; they are removed by the purge script (§2.6) rather than left to rot, since they predate the P0-2 fix and cannot be trusted anyway (see §2.6).

**Reversibility**: down-migration is `ALTER TABLE embeddings DROP COLUMN model|dim|last_accessed_at`, supported since SQLite 3.35.0 (2021-03-12, per SQLite's own release notes — source 1) and confirmed present on this machine: `python -c "import sqlite3; print(sqlite3.sqlite_version)"` → `3.53.3` (source 2, live probe). Documented in the migration's docstring; not scripted (single-file, single-table, low-risk enough for a manual command if ever needed).

### 2.6 Why the purge is whole-table, not selective

The schema before this fix stores only `key TEXT` (a hash) and `vector TEXT` — no original text or its length. There is no query that can distinguish "this row's vector was computed correctly (original text ≤200 chars)" from "this row is poisoned (original text >200 chars, only its first 200 chars were ever embedded)" after the fact — the hash is one-way and the length information was never persisted. Selective purge would require guessing, which fails AGENTS.md §1 ("nothing simulated... no claim without executable proof"). A full purge is the only provably-correct option; the cache is a pure derived-data store (SQLite row loss here means one recompute per memory on next access, not data loss of source-of-truth content), so the blast radius of wiping it is a latency blip, not corruption.

### 2.7 Eviction policy

`EMBEDDING_CACHE_MAX_ROWS` (new env var, default `50000`, read directly via `os.getenv` for consistency with this file's existing direct-env-var style — it does not currently import `shared.config.Config`, and adding that coupling is out of scope for a surgical P0 fix). On every `cache_set`, after the insert/replace, if `SELECT COUNT(*) FROM embeddings` exceeds the cap, delete the oldest-`last_accessed_at` rows down to the cap in one `DELETE ... WHERE key IN (SELECT key FROM embeddings ORDER BY last_accessed_at ASC LIMIT ?)` statement — bounded, single round trip, still inside the existing `_db_lock`. `cache_get` updates `last_accessed_at = strftime('%s','now')` on hit so the policy is true LRU, not insertion-order.

**Alternative considered**: TTL-based expiry (delete rows older than N days). Rejected as the primary mechanism — embeddings for unchanged text under an unchanged model never go stale by time, only by model swap (already handled by the key format in §2.4) or by row-count pressure (handled here). Row-count cap is the correct bound for "don't let the file grow forever" without punishing long-lived-but-still-valid entries.

## 3. Test strategy (per iteration, red→green per `openspec/AGENTS.md` §3)

- `tests/core/test_embedding.py`: a stub `EmbeddingBackend` recording every `embed()` call's argument; assert full text (>200 chars, ≤2000) reaches it unmodified; assert a >2000-char text triggers exactly one `WARNING` log record with before/after lengths (via `caplog`); assert `model_id` per concrete backend matches the table in §2.3 (constructed with a fixed model path/env, no real subprocess/network — mirrors the `httpx.MockTransport` test-only-DI pattern already used in `tests/core/test_llm_ollama.py`).
- `tests/core/test_embedding_cache.py`: temp SQLite file per test (`tmp_path` fixture, never `~/.memory`); assert key format changes across `(model_id, dim)` pairs for identical text; assert schema migration is idempotent (`_migrate_schema` run twice on the same connection doesn't error); assert `EMBEDDING_CACHE_MAX_ROWS` eviction removes the least-recently-accessed rows first, keeps the cap.
- `tests/core/test_purge_embedding_cache.py` (or a `bin/` script test if the repo's convention places script tests there — confirmed by checking `tests/` layout during I05, no existing `bin/*` test precedent found as of this writing): populate a temp DB, run the script's main function directly (importable, not only CLI) with `--dry-run` (asserts row count unchanged, no backup written) and without (asserts backup file exists with pre-purge row count, live table is empty).

## 4. Rollout note

This fix does not require restarting Qdrant or touching existing vectors already upserted there — it only affects future embedding calls and the *local* SQLite embedding cache. The purge script is opt-in (must be run explicitly), not triggered automatically by the code fix, so existing poisoned cache rows remain until Rubén runs it — call this out explicitly when reporting the implementation iterations, per AGENTS.md §1 (no silent degradation, no silent fix-and-forget either).
