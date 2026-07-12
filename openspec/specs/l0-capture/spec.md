# Spec — l0-capture

Status: current | Last-verified: 2026-07-12

> Source: `src/L0_capture/server/main.py` (158 lines). Registered into the unified MCP server with prefix `L0_capture_`.

## Capability: real-time memory ingestion

Entry point for all raw activity and LLM-judged memories. Backs the L0 (raw JSONL, append-only) and L1 (working, Qdrant) layers.

### Tools (verified against source)

| Tool | Behavior |
|------|----------|
| `L0_capture_memorize(content, mem_type, scope, scope_id, importance, tags)` | LLM-judgment call. Sanitizes input (`validate_memorize`), builds a `MemoryItem` (layer=WORKING), stores it via `_store_memory`, appends an `AGENT_ACTION` event to the L0 JSONL. |
| `L0_capture_ingest_event(event_type, source, content, actor_id, session_id)` | Always appends a `RawEvent` to L0 JSONL first (never lost). If content >20 chars or is a `diff_*` event, also stores a truncated (2000 char) `MemoryItem` to L1. |
| `L0_capture_heartbeat(agent_id, session_id, turn_count, prefetch_queries)` | Writes `data/L1-working/{agent_id}.json` status file; best-effort background prefetch of embeddings; calls `model_tier.maybe_refresh()` (cheap no-op unless TTL expired); returns `promotion_due` when `turn_count % PROMOTION_INTERVAL == 0`. |
| `L0_capture_status()` | Reports Qdrant health, llama.cpp binary presence, raw-event count (line count of the JSONL file), stored-memory count, staged change-set count. |

### Storage

- `_store_memory`: `qdrant.ensure_collection()` → `safe_embed(content)` (or reuse `item.embedding` if precomputed) → `qdrant.upsert()`. On **any** exception, falls back to appending a `SYSTEM` event to the L0 JSONL with the error — raw data is never lost, but the memory is not searchable until reprocessed (no reprocessing job exists today).

### Known defects (inherited from shared dependencies, still present — see `embedding-pipeline` spec for detail)

- `safe_embed()` failure path returns a zero-vector that `_store_memory` happily upserts as a valid point (P0-4).
- `qdrant.upsert()` never checks the HTTP response status (P0-6 in `shared/qdrant_client.py`), so a Qdrant-side rejection is indistinguishable from success at this layer.
- `_store_memory`'s `except Exception` is broad; any transient error (including validation errors from a malformed `MemoryItem`) is silently downgraded to a JSONL-only write.

### Test coverage

No dedicated handler tests found for this module's MCP tool functions (matches testing-audit finding P1: "6/7 Lx module handlers 0 tests").
