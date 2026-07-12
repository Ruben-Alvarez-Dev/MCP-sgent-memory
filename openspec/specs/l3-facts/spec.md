# Spec — l3-facts

Status: current | Last-verified: 2026-07-12

> Source: `src/L3_facts/server/main.py` (77 lines). Registered with prefix `L3_facts_`. Qdrant collection `L3_facts`.

## Capability: per-user semantic memory CRUD

Simple fact store: one Qdrant collection, points tagged with `user_id` in the payload. No per-user collection or namespace isolation at the Qdrant level — isolation is enforced entirely in application code.

### Tools (verified against source)

| Tool | Behavior |
|------|----------|
| `L3_facts_add_memory(content, user_id, metadata)` | Sanitizes input, embeds via `safe_embed`, computes BM25 sparse vector, upserts to Qdrant with a random UUID4 id. |
| `L3_facts_search_memory(query, user_id, limit, min_score)` | Embeds the query, calls `qdrant.search(vector, limit, score_threshold)` **without a `user_id` filter**, then filters the returned page down to matching `user_id` in Python. |
| `L3_facts_get_all_memories(user_id, limit)` | `qdrant.scroll()` with a proper server-side `user_id` filter. |
| `L3_facts_delete_memory(memory_id, user_id)` | Fetches the point, checks `user_id` ownership in Python, then deletes. |
| `L3_facts_status()` | Qdrant health + total point count (not per-user). |

### Known defect (verified 2026-07-12, not previously in the audit list — found during this review)

- **`search_memory` filters after limiting, not before**: Qdrant is asked for the top `limit` results across *all* users, and only then are non-matching-`user_id` rows dropped. In a multi-user deployment with more than a handful of users, a user's own relevant memories can rank outside the initial `limit` window and never reach the client, even though `get_all_memories`/`qdrant.scroll` prove they exist. Qdrant supports a native payload filter on `search()` (used correctly by `search_conversations` in `l2-conversations`); this handler does not use it.

### Storage

Single flat Qdrant collection `L3_facts`, dim = `config.embedding_dim` (1024). Inherits `embedding-pipeline` known defects (truncation, zero-vector-on-failure, unverified writes) for every `add_memory` call.

### Test coverage

Handler-level tests not found for this module (P1: 6/7 Lx module handlers 0 tests).
