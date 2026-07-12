# Change: honest-l2-status

- **Status**: proposed — planning only, awaiting Rubén's approval before numbered iterations start (AGENTS.md §4)
- **Owner**: backend · **Release**: v2.2.0 (Phase 2, wave 1) · **Addresses**: P0-5

## Why

`save_conversation` (`src/L2_conversations/server/main.py`) wraps the Qdrant embed+upsert step in a bare `try/except Exception` that only logs a warning, then unconditionally returns `SaveConversationResult(status="saved", ...)` regardless of whether the vector write actually succeeded. SQLite (primary storage) does save correctly, but the vector silently does not — the caller has no way to know semantic search will never find this thread. Current code (line numbers shifted from the audit's `82-91` since P0-5 was logged):

```
src/L2_conversations/server/main.py:61-86   # try/except around embed+upsert, logger.warning only
src/L2_conversations/server/main.py:88-91   # unconditional `status="saved"` return
```

This violates AGENTS.md §1 ("no silent degradation: every fallback must log loudly and surface in health_check/result payloads") — today it only logs, it does not surface.

## What

1. `shared/result_models.py`: `SaveConversationResult` gains two fields — `degraded: bool = False` and `qdrant_error: str | None = None` — and a new `status="saved_sqlite_only"` value (SQLite ok, Qdrant write failed), alongside the existing `status="saved"` (both stores ok). `status` stays plain `str` (matching every other result model in this file — no `Literal` is used anywhere in `shared/result_models.py`), values documented in the field docstring.
2. `src/L2_conversations/server/main.py::save_conversation`: on the Qdrant except branch, build and return the degraded result instead of falling through to the unconditional `status="saved"` return; docstring updated to document both status values for MCP tool callers.
3. HTTP sidecar (`shared/api_server.py`, `/api/save-conversation`): no code change expected — `_serialize()` already calls `result.model_dump()` (`shared/api_server.py:309-315`) and `_json_response` is always `200` regardless of tool status for every other endpoint too (existing repo-wide pattern, not something this change alters). A contract test locks in that the new fields actually reach the JSON body (currently unverified — no sidecar test exists for this endpoint).
4. No logging changes, no Qdrant client changes — see `design.md` for the two residual honesty gaps this proposal does **not** close (P0-6 `qdrant-write-integrity`, P0-4 `no-zero-vectors`) and the P0-7 `logging-root-fix` interaction.

## Spec delta note

`openspec/specs/conversation-store/` does not exist yet (only `openspec/specs/model-stack/` has been backfilled as of this proposal — Phase 1 baseline is in progress on a concurrent task). The delta at `openspec/changes/honest-l2-status/specs/conversation-store/spec.md` is written as a **self-contained target end-state** description. Reconcile it into the Phase 1 baseline `openspec/specs/conversation-store/spec.md` once that lands — do not block this change on it.

## Acceptance

- Qdrant reachable, embed+upsert succeed: `save_conversation` returns `status="saved"`, `degraded=False`, `qdrant_error=None` (unchanged happy path, regression-tested).
- Qdrant down (connection refused) or `ensure_collection`/`upsert` raises: SQLite thread still exists (`get_thread` finds it) AND `save_conversation` returns `status="saved_sqlite_only"`, `degraded=True`, `qdrant_error` populated with a bounded, typed message (dual check: return value + independent SQLite read).
- `/api/save-conversation` JSON response reflects the same degraded fields (sidecar contract test, ASGI-free `BaseHTTPRequestHandler` test per existing sidecar test conventions).
- Unit tests only — no real Qdrant/embedding service required (Qdrant client + `safe_embed` are patched/stubbed to raise, matching the dual-validation table in `openspec/AGENTS.md` §2 "Bug diagnosis: reproducing it + locating the causal line(s) in code").
