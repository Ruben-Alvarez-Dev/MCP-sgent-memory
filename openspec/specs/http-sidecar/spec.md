# Spec — http-sidecar

Status: current | Last-verified: 2026-07-12

> Source: `shared/api_server.py` (364 lines). Started from `unified/server/main.py::main()` (the stdio MCP entrypoint) in a background thread, and independently from the standalone daemon `unified/server/backpack.py`. Port: `AUTOMEM_API_PORT` env, default 8890.

## Capability: plugin-to-server HTTP bridge

Lets the (not-yet-recovered, see `project.md` glossary) `backpack-orchestrator` OpenCode plugin trigger MCP tool functions via `fetch()` without an LLM turn. Implemented with stdlib `http.server.HTTPServer` (NOT `ThreadingHTTPServer`) + one background thread — **requests are handled one at a time**, sequentially, including the up-to-20-sequential-httpx-call `verify-memories` batch.

### Endpoints (verified against source — this is the real, current contract; no OpenAPI spec exists yet)

| Method | Path | Delegates to |
|--------|------|---------------|
| GET | `/api/health` | static endpoint list |
| GET | `/api/model-tier` | `shared.model_tier.status()` (fresh probe) |
| POST | `/api/ingest-event` | `L0_capture.ingest_event(**body)` |
| POST | `/api/heartbeat` | `L0_capture.heartbeat(**body)` |
| POST | `/api/heartbeat-dream` | `L0_to_L4_consolidation.heartbeat(**body)` |
| POST | `/api/save-conversation` | `L2_conversations.save_conversation(**body)` |
| POST | `/api/consolidate` | `L0_to_L4_consolidation.consolidate(**body)` |
| POST | `/api/request-context` | `L5_routing.request_context(**body)` (optional; 404 if module failed to load) |
| POST | `/api/verify-memories` | local `_verify_memories()` — talks to Qdrant directly via `httpx`, not through a registered MCP tool |

Every handler runs on a single persistent asyncio event loop per process (`_run_async`), reused across requests (not per-request), shared with whichever thread `start_api_server` was called from.

### Known defects (confirmed present, 2026-07-12 direct read)

- **No input validation / no `/v1` versioning**: `_run_async(_fn(**body))` — a malformed or missing field raises a bare `TypeError`, caught by a blanket `except Exception` and returned as HTTP 500 with `str(e)` as the only detail. No JSON Schema/OpenAPI contract exists despite `docs/plan/IMPROVEMENT-PLAN.md` §3.2 naming OpenAPI 3.1 + FastAPI as the target standard — that target is **not implemented**.
- **CORS wildcard**: `Access-Control-Allow-Origin: *` on every response (`_json_response`, `do_OPTIONS`) — acceptable only because the server binds `127.0.0.1` only (confirmed: `HTTPServer(("127.0.0.1", port), ...)`), not `0.0.0.0`.
- **Duplicate startup paths (P1)**: the sidecar is started identically from both `unified/server/main.py::main()` and the standalone `unified/server/backpack.py` daemon — running both against the same port double-binds and fails; ADR-0005 designates `backpack.py` as the single intended owner, not yet enforced in code.
- **`gateway.py`** (a third, HTTP-to-stdio bridge, unrelated port) imports `aiohttp`, which is not declared in `pyproject.toml` — dead/broken unless installed out-of-band (P1, architect audit).

### Test coverage

No sidecar contract tests found under `tests/` (P0-12 / P1: "HTTP sidecar 0 tests").
