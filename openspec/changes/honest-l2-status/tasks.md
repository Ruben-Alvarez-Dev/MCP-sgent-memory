# Tasks — honest-l2-status

Each item below is one numbered iteration (`I01`, `I02`, ... per `openspec/AGENTS.md` §4) once this proposal is approved. Red→green evidence goes in `evidence/I<NN>.md`, committed with the iteration. No iteration starts before the previous one is DONE.

- [ ] 1. `shared/result_models.py`: add `degraded: bool = False` and `qdrant_error: str | None = None` to `SaveConversationResult`; document the two `status` values (`"saved"`, `"saved_sqlite_only"`) in a field/class docstring.
      Red: a model-construction test asserting the new fields exist with the stated defaults (fails today — `AttributeError`/`ValidationError`, fields don't exist).
      Green: fields added; test passes; no other model in the file changes.
      Scope: pure pydantic model, no I/O — smallest independently-testable unit.

- [ ] 2. `src/L2_conversations/server/main.py::save_conversation`: replace the unconditional `return SaveConversationResult(status="saved", ...)` with the degraded-aware return described in `design.md` (`degraded`/`qdrant_error` set inside the `except Exception as e` branch, `status="saved_sqlite_only"` when degraded); update the tool docstring to document both status values for MCP callers.
      Red: two tests — (a) happy path with Qdrant mocked/stubbed to succeed still returns `status="saved", degraded=False, qdrant_error=None` (regression guard, should already pass — write it first to lock current behavior before touching the code); (b) Qdrant failure path (patch `qdrant.upsert` — or `qdrant.ensure_collection` — to raise) asserts `status="saved_sqlite_only"`, `degraded=True`, `qdrant_error` is a non-empty bounded string, AND independently asserts via `get_thread(thread_id)` that SQLite still has the thread (dual validation: return value + independent read, per AGENTS.md §2). Test (b) fails against current code (`status` is always `"saved"`).
      Green: both tests pass after the code change; `logger.warning` call path unchanged (verify via existing behavior, no new logging assertion needed — see design.md gap #3).
      No changes to `shared/qdrant_client.py` or `shared/embedding.py` in this iteration (P0-6/P0-4 are separate changes — see design.md residual gaps).

- [ ] 3. HTTP sidecar contract test for `/api/save-conversation`: register a stub `save_conversation_fn` (via `register_endpoints`/module-level setter, matching existing sidecar test conventions if `tests/core/test_api_server.py` or similar exists — otherwise a minimal new test file) that returns a `SaveConversationResult(status="saved_sqlite_only", degraded=True, qdrant_error="...")`, POST to `/api/save-conversation`, assert the JSON response body contains `degraded: true` and the `qdrant_error` string, and explicitly assert the HTTP status code is still `200` (locking in the documented out-of-scope decision in `design.md`, not an oversight).
      Red: test fails today only in the sense that the endpoint/fixture wiring may not exist yet for this tool — if `tests/core` already covers `/api/save-conversation` for the happy path, extend that file; write the assertion first against the *current* two-field model to confirm it fails on the missing `degraded`/`qdrant_error` keys, then re-run after task 1+2 land.
      Green: fields present in the response body; status code assertion passes (200, unchanged).
      No production code change expected in `shared/api_server.py` (see design.md — propagation is free via `model_dump()`); if the test proves otherwise, that's new information — stop and report the discrepancy per AGENTS.md §2 before proceeding.

- [ ] 4. Full-suite check + spec archive prep: `PYTHONPATH=src .venv/bin/python -m pytest tests/core -q` green, `ruff check src tests` clean, then tick this file's boxes and leave the change ready for archival into `openspec/specs/conversation-store/` (reconciled with the Phase 1 baseline per the note in `proposal.md`) once Rubén approves.
      Not a code iteration — verification + bookkeeping only, still requires its own evidence file (full-suite command + output).

## Explicitly out of scope for this change's iterations (tracked elsewhere)

- P0-6 `qdrant-write-integrity`: `raise_for_status()` on `upsert`/`upsert_batch`.
- P0-4 `no-zero-vectors`: `safe_embed` typed failure instead of zero-vector fallback.
- P0-7 `logging-root-fix`: `agent-memory.*` logger namespace fix for L2 (and other modules using `getLogger(__name__)`).
