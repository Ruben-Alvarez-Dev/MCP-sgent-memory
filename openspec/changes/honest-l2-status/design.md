# Design — honest-l2-status

## Current code (verified 2026-07-12, HEAD of `change/phase0-foundation`)

`src/L2_conversations/server/main.py`:

```python
# 1. SQLite — full messages + metadata + scope (primary storage)
save_thread(clean["thread_id"], messages, summary, agent_scope=agent_scope)   # :58

# 2. Qdrant — vector for semantic search (best-effort, non-blocking)
try:                                                                          # :61
    ...
    vector = await safe_embed(text_for_embedding)                            # :65
    ...
    await qdrant.ensure_collection(sparse=True)                              # :67
    ...
    await qdrant.upsert(point_id, vector, {...}, sparse=sparse)              # :71-81
except Exception as e:                                                       # :82
    logger.warning(                                                          # :83-86
        "Qdrant upsert failed for thread %s (SQLite saved OK): %s",
        clean["thread_id"], e
    )

return SaveConversationResult(status="saved", thread_id=clean["thread_id"])  # :88-91
```

The `return` is outside (after) the try/except and unconditional — success or failure of the Qdrant branch never changes it.

## Target model change

`shared/result_models.py::SaveConversationResult` — current:

```python
class SaveConversationResult(BaseModel):
    status: str = "saved"
    thread_id: str
```

Target:

```python
class SaveConversationResult(BaseModel):
    status: str = "saved"          # "saved" | "saved_sqlite_only"
    thread_id: str
    degraded: bool = False         # True when Qdrant write failed; SQLite is still authoritative
    qdrant_error: str | None = None  # f"{type(e).__name__}: {e}", bounded (e.g. [:300]) when degraded
```

Matches the plain-`str` `status` convention used by every other result model in the same file (`MemorizeResult`, `IngestResult`, `HeartbeatResult`, etc. — none use `Literal`); no new dependency, no schema-breaking rename of `status="saved"` for the happy path.

## Target control flow

```python
degraded = False
qdrant_error = None
try:
    ...
except Exception as e:
    degraded = True
    qdrant_error = f"{type(e).__name__}: {e}"[:300]
    logger.warning(
        "Qdrant upsert failed for thread %s (SQLite saved OK): %s",
        clean["thread_id"], e
    )

return SaveConversationResult(
    status="saved_sqlite_only" if degraded else "saved",
    thread_id=clean["thread_id"],
    degraded=degraded,
    qdrant_error=qdrant_error,
)
```

`logger.warning` call is unchanged (still fires) — this proposal only changes what the *return value* says, not the logging path (see gap #3 below).

## HTTP sidecar propagation

`shared/api_server.py:258-260` calls `_run_async(_save_conversation_fn(**body))` then `_json_response(200, self._serialize(result))`. `_serialize` (`:309-315`) does `result.model_dump()` for anything with that attribute — so the new fields reach the JSON body **without any sidecar code change**, purely from extending the Pydantic model. What this proposal does *not* change: the sidecar always responds HTTP `200` regardless of the tool's internal status (true for every endpoint in this file, not just this one — see `/api/model-tier`'s `except Exception` at `:234-236` still returning `500` only for a handler-level exception, never for a tool-level degraded result). Mapping `degraded=True` to a non-200 status code would be a sidecar-contract-wide decision (touches every endpoint, likely lands with the FastAPI `/v1` migration in Phase 3 per `docs/plan/IMPROVEMENT-PLAN.md` §4 Phase 3) — explicitly out of scope here. This proposal's honesty guarantee is at the **response-body** level only.

## Residual honesty gaps — explicit, not silently deferred

AGENTS.md §1 forbids claiming something works without proof and forbids silent degradation. Two sibling P0s bound what this change can actually detect; documenting them here so the acceptance criteria in `proposal.md` aren't overclaimed.

1. **P0-6 `qdrant-write-integrity` (separate change, not touched here)**: `QdrantClient.upsert()`'s inner `_do()` (`src/shared/qdrant_client.py:198-205`) calls `client.put(...)` and never calls `resp.raise_for_status()` — httpx does not raise on non-2xx by default. A Qdrant-side HTTP error response (e.g. 400 malformed point, 500) on the actual point write is silently swallowed **before** it ever reaches this change's `except Exception`. Contrast with `ensure_collection` (`:115-120`), which *does* call `resp.raise_for_status()` and therefore *is* caught correctly today. Until `qdrant-write-integrity` adds `raise_for_status()` to `upsert`/`upsert_batch`, a subset of Qdrant write failures will still incorrectly return `status="saved"` after this change lands. Not fixed here — flagged as a known residual gap in `proposal.md`'s acceptance section.
2. **P0-4 `no-zero-vectors` (separate change, not touched here)**: `safe_embed()` (`src/shared/embedding.py:600-616`) never raises on embedding failure — it logs a warning and returns `[0.0]*dim`, which then upserts "successfully" (no exception, `resp.raise_for_status()` on `ensure_collection` unaffected, the point PUT itself isn't checked per gap #1 either way). This change's except block cannot detect a zero-vector write because no exception is thrown. `status="saved"` (not `saved_sqlite_only`) is still returned even though the stored vector is corrupt/unsearchable. Same caveat applies to `proposal.md` acceptance.
3. **P0-7 `logging-root-fix` (separate, later Phase 2 change)**: `src/L2_conversations/server/main.py:15,28` uses `logging.getLogger(__name__)` (i.e. `L2_conversations.server.main`), not the `agent-memory.*` namespace that `shared/logging_config.py:18` (`logging.getLogger("agent-memory")`) actually attaches handlers to. The existing `logger.warning(...)` at the Qdrant-failure site (unchanged by this proposal) therefore never reaches `~/.memory/server.log` today — it only reaches stderr if a root handler happens to be attached elsewhere, which for the MCP stdio server it is not. **This proposal does not depend on the log line for its honesty guarantee** — the `degraded`/`qdrant_error`/`status` fields on the returned/serialized result are the source of truth and are independently assertable in tests without capturing logs, which is why this change can land before `logging-root-fix` without weakening its own acceptance criteria. Once `logging-root-fix` lands, the same warning will additionally become visible in `server.log` for free (no code change needed here for that to happen) — noted for the implementer of that later change so they don't need to touch L2 again for this specific line.

## Non-goals

- No change to `qdrant.upsert`/`ensure_collection` error-raising behavior (P0-6).
- No change to `safe_embed`'s zero-vector fallback (P0-4).
- No change to logger namespace or `setup_logging` (P0-7).
- No HTTP status code change on the sidecar (Phase 3 FastAPI migration territory).
- No retry/backoff changes to the Qdrant write path itself (already handled by `QdrantClient._retry`, unchanged).
