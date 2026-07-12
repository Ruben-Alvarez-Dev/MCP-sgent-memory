# Spec — l2-conversations

Status: current | Last-verified: 2026-07-12

> Source: `src/L2_conversations/server/main.py` (212 lines), `shared/conversation_db.py`. Registered with prefix `L2_conversations_`.

## Capability: conversation thread persistence & search

Dual storage: SQLite + FTS5 is the primary, authoritative store (full messages, exact retrieval); Qdrant holds a best-effort semantic vector per thread. Multi-agent isolation via `agent_scope` ("shared" or an agent-specific scope; search returns own scope + "shared").

### Tools (verified against source)

| Tool | Behavior |
|------|----------|
| `L2_conversations_save_conversation(thread_id, messages_json, summary, agent_scope)` | 1) `save_thread()` to SQLite (delete-and-replace semantics). 2) Best-effort: embed `summary` or first 5 messages (2000-char cap), `qdrant.upsert()` with a deterministic UUIDv5 point id from `thread_id`. Qdrant step is wrapped in `try/except Exception → logger.warning`. |
| `L2_conversations_get_conversation(thread_id)` | Reads from SQLite only. |
| `L2_conversations_search_conversations(query, limit, min_score, agent_scope)` | Merges Qdrant semantic results (scope-filtered via Qdrant `should` filter) with SQLite FTS5 results; dedupes by `thread_id`, Qdrant hits take priority. |
| `L2_conversations_list_threads(limit, agent_scope)` | SQLite only, ordered by last update. |
| `L2_conversations_status()` | Qdrant health + SQLite thread count. |

### Known defects (confirmed present, 2026-07-12 direct read)

- **False "saved" status (P0-5)**: `save_conversation` always returns `SaveConversationResult(status="saved", ...)` regardless of whether the Qdrant upsert succeeded — the `except` branch only logs a warning, never surfaces failure to the caller. A thread can be fully searchable-blind (SQLite-only) while every caller believes it was saved with its vector.
- **Logger not in the `agent-memory.*` tree**: `logger = logging.getLogger(__name__)` (line 28) resolves to `L2_conversations.server.main`, which `shared/logging_config.setup_logging()` does not configure — the Qdrant-failure warning above is silently dropped from `server.log` in normal operation (part of P0-7, logging tree broken).
- **`save_thread` is delete-and-replace**: re-saving a thread invalidates prior SQLite message ids (P1 finding, database audit) — not verified line-by-line here, carried from `docs/plan/IMPROVEMENT-PLAN.md` §2.2.

### Test coverage

Handler-level tests not found for this module (P1: 6/7 Lx module handlers 0 tests).
