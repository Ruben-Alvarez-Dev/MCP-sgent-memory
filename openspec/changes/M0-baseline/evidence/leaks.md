# Leak inventory (re-confirmed 2026-09-06, code inspection + tests)

| ID | Finding | Evidence | Severity |
|---|---|---|---|
| L-R1 | `_get_reminders(agent_id)` ignores `agent_id`, returns ALL `*.json` | `src/L5_routing/server/main.py:25` | HIGH — any agent lists all reminders |
| L-D1 | `_retrieve_L3_decisions` reads all `*.md`, no scope filter | `src/shared/retrieval/__init__.py:281-306` | HIGH — decisions visible cross-scope via `request_context` |
| L-F1 | `search_memory` filters `user_id` in Python post-search; other read paths unfiltered | `src/L3_facts/server/main.py:33-49` | MEDIUM — bypass via pagination/limits, timing oracle |
| L-C1 | Consolidation writes `scope_id=consolidated/narrative/dream` with no provenance | `src/L0_to_L4_consolidation/server/main.py:87,102,271` | HIGH — designed-in scope mixing |
| L-V1 | Vault + decisions are global filesystem, no namespace | `src/L3_decisions/server/main.py:13-14`, `bin/vault_processor.py` | HIGH — any path read reaches all notes |
| L-ID0 | No identity layer: all scopes self-asserted, no auth | whole `src/` (no auth anywhere; Qdrant localhost-only, no creds) | CRITICAL (structural) — all enforcement is advisory until M4 trusted identity |
| ISO-08 | `ScopedQdrantClient`/`HybridQdrantClient` pass isolation tests but NO hot path uses them | `tests/core/test_agent_scope_qdrant.py` 6/6 PASS vs `grep` usage in modules = 0 | MEDIUM — dead security code creates false confidence |

Note: scope tests passing (6/6) proves the *clients* isolate; it does NOT prove the
*system* isolates. M1 must test through MCP tool entrypoints, not client classes.
