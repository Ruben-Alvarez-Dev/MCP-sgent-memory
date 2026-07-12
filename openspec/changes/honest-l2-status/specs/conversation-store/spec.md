# Spec delta — conversation-store (honest-l2-status)

> **Self-contained target end-state.** `openspec/specs/conversation-store/spec.md` does not exist yet — the Phase 1 baseline backfill is in progress on a concurrent task. Reconcile this delta into that baseline once it lands (see `proposal.md`); do not block this change on it. Written against the current implementation in `src/L2_conversations/server/main.py` + `shared/result_models.py::SaveConversationResult`.

## Capability: honest save-conversation status

`save_conversation` writes to two independent stores — SQLite (primary, exact retrieval + FTS5) and Qdrant (secondary, semantic search only). A partial write (SQLite ok, Qdrant not) SHALL be visible to every caller of the tool and of the HTTP sidecar; it MUST NOT be reported as an unqualified success.

### ADDED Requirement: `SaveConversationResult` reflects per-store outcome

The result returned by `save_conversation` (MCP tool) and by `POST /api/save-conversation` (HTTP sidecar, same payload via `model_dump()`) SHALL carry:

| Field | Type | Meaning |
|---|---|---|
| `status` | `str` | `"saved"` — both SQLite and Qdrant writes succeeded. `"saved_sqlite_only"` — SQLite succeeded, Qdrant write raised (embedding, collection-ensure, or upsert step). |
| `thread_id` | `str` | Unchanged — the saved thread's id. |
| `degraded` | `bool` | `True` iff `status == "saved_sqlite_only"`. Redundant with `status` by design (machine-checkable boolean alongside a human-readable string, matching the `health_check`/`degraded` convention used elsewhere in the repo per `openspec/AGENTS.md` §1). |
| `qdrant_error` | `str \| None` | `None` when `degraded` is `False`. A bounded (≤300 char) `f"{type(exc).__name__}: {exc}"` string when `degraded` is `True`. Never `None` when `degraded` is `True`. |

#### Scenario: Qdrant reachable, embed+upsert succeed

- **GIVEN** a valid `thread_id` and `messages_json`, Qdrant reachable, embedding backend reachable
- **WHEN** `save_conversation` is called
- **THEN** the thread is retrievable via `get_thread(thread_id)` (SQLite) AND searchable via `search_conversations` (Qdrant, semantic match)
- **AND** the returned result has `status="saved"`, `degraded=False`, `qdrant_error=None`

#### Scenario: Qdrant write fails (connection error, timeout-after-retry, `ValueError` from payload/dimension validation, or `ensure_collection` HTTP error)

- **GIVEN** a valid `thread_id` and `messages_json`, the Qdrant write path raises during `ensure_collection` or `upsert`
- **WHEN** `save_conversation` is called
- **THEN** the thread is still retrievable via `get_thread(thread_id)` (SQLite unaffected — writes are sequential, SQLite first)
- **AND** the thread is NOT found by `search_conversations` semantic search (no vector was written)
- **AND** the returned result has `status="saved_sqlite_only"`, `degraded=True`, `qdrant_error` populated with a non-empty bounded string identifying the failure
- **AND** a `WARNING`-level log line is emitted at the failure site (visibility in `~/.memory/server.log` depends on the separate `logging-root-fix` change — not guaranteed by this requirement alone)

#### Scenario: HTTP sidecar propagates the same result

- **GIVEN** the conditions of either scenario above, invoked via `POST /api/save-conversation` instead of the MCP tool directly
- **WHEN** the sidecar handler runs
- **THEN** the JSON response body contains the same `status`/`degraded`/`qdrant_error`/`thread_id` fields as the MCP tool would return (no field is dropped or renamed by `_serialize`)
- **AND** the HTTP status code is `200` in both the success and degraded cases (the sidecar does not map application-level degradation to a non-2xx HTTP status in this iteration — that is a separate, sidecar-contract-wide decision, out of scope here)

### Known non-guarantees (explicit, cross-referenced to sibling P0s)

This capability's honesty guarantee is **bounded** by two conditions that this change does not fix:

- A Qdrant-side HTTP error response on the point-upsert PUT itself is currently not raised as an exception (no `raise_for_status()` on that call) and therefore is NOT caught — `status="saved"` may still be wrongly reported in that specific case until `qdrant-write-integrity` (P0-6) lands.
- A zero-vector fallback from the embedding backend does not raise — a point IS written to Qdrant (with a corrupt, unsearchable zero vector) and `status="saved"` is reported, not `"saved_sqlite_only"`, until `no-zero-vectors` (P0-4) lands.

These are documented, not silently accepted — see `design.md` for the full analysis.
