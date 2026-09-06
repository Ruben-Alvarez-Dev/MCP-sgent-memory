"""
Backpack HTTP API — Lightweight sidecar for plugin-to-server communication.

Runs alongside the MCP stdio server in a background thread.
Plugin hooks call these endpoints via fetch() to trigger automatic memory
operations without involving the LLM.

Architecture:
    OpenCode hooks → fetch() → http://127.0.0.1:8890/api/* → Python functions → MemoryDB

Uses stdlib http.server + threading — same pattern as observe.py dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable

from shared.memory_db import MemoryDB

logger = logging.getLogger("agent-memory.api")

# ── Module-level function references ─────────────────────────────────
# Set by start_api_server() before the HTTP server starts.
# These point to the SAME functions registered as MCP tools — zero duplication.

_ingest_event_fn: Callable | None = None
_L0_capture_heartbeat_fn: Callable | None = None
_L0_to_L4_consolidation_heartbeat_fn: Callable | None = None
_save_conversation_fn: Callable | None = None
_consolidate_fn: Callable | None = None
_request_context_fn: Callable | None = None

# v1.5: verify-memories uses MemoryDB (SQLite engine) directly — no MCP tool needed.
# Qdrant is demolished; reads go through MemoryDB.scroll/get with a MANDATORY
# engine filter (fail-closed). L0_L4_memory rows are written with
# agent_scope="shared" (see L0_capture._store_memory), so "shared" is the scope.
_VERIFY_COLLECTION = "L0_L4_memory"

_verify_db: MemoryDB | None = None  # lazy — keeps module import side-effect free


def _get_verify_db() -> MemoryDB:
    """Lazily build the MemoryDB handle for the verify endpoint."""
    global _verify_db
    if _verify_db is None:
        from shared.config import Config
        from shared.memory_db import MemoryDB

        _verify_db = MemoryDB(None, _VERIFY_COLLECTION, Config.from_env().embedding_dim)
    return _verify_db


def _set_payload_sync(db: MemoryDB, point_id: str, payload: dict) -> int:
    """Legacy set_payload parity (Qdrant API shape): payload column only.

    MemoryDB.upsert(vector=None) would NULL the stored embedding
    (ON CONFLICT ... vector=excluded.vector), wiping the vector on every
    verification cycle. This narrow UPDATE touches payload only — vector,
    agent_scope, user_id and created_at columns stay intact. Same connection
    and lock discipline as MemoryDB._upsert_one. Precedent for direct engine
    access where the public API can't express the operation: _verify_stale()
    in L0_to_L4_consolidation (ISO-11: payload keys are not filterable).
    Merged keys are pre-validated payload keys + standard verification fields,
    so skipping _validate_payload_keys is safe.
    """
    with db._lock, db._conn:
        cur = db._conn.execute(
            "UPDATE points SET payload=? WHERE collection=? AND id=?",
            (json.dumps(payload), db.collection, point_id),
        )
        return cur.rowcount


async def _verify_memories(body: dict) -> dict:
    """v1.5: Verify memories against current state (MemoryDB backend).

    For each memory (or stale memories in scope):
    1. Fetch from MemoryDB
    2. Check if the fact is still true (file_check for slow/fast)
    3. Update verified_at, verification_status, access_count

    Returns counts: verified, stale, errors.
    """
    from datetime import datetime, timezone

    db = _get_verify_db()
    await db.ensure_collection()

    memory_ids = body.get("memory_ids", [])
    scope = body.get("scope", "")

    if not memory_ids and not scope:
        # Auto-mode: find stale memories to verify.
        # Engine filter is MANDATORY on scroll (fail-closed). 'verification_status'
        # is a payload key, not engine-filterable (ISO-11) — the scope predicate
        # lives INSIDE the engine filter; the status predicate is applied only to
        # the already agent_scope-scoped result set (no unscoped read happens).
        try:
            rows = await db.scroll(
                filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                limit=50,
            )
            memory_ids = [
                p["memory_id"]
                for p in rows
                if p.get("memory_id")
                and p.get("verification_status", "never_verified")
                in ("never_verified", "verified")
            ]
        except Exception:
            pass

    if not memory_ids:
        return {"verified": 0, "stale": 0, "errors": [], "message": "no memories to verify"}

    verified_count = 0
    stale_count = 0
    errors = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for mid in memory_ids[:20]:  # Cap at 20 per batch
        try:
            # Fetch the point
            rec = await db.get(mid, filter={"must": [{"key": "agent_scope", "match": {"any": ["shared", "merged"]}}]})
            if rec is None:
                errors.append(f"not found: {mid}")
                continue

            payload = rec.get("payload", {})
            speed = payload.get("change_speed", "slow")
            status = payload.get("verification_status", "never_verified")
            current_access = payload.get("access_count", 0)

            # Verification logic based on change_speed
            new_status = "verified"
            verification_source = "file_check"

            if speed == "realtime":
                # Realtime facts are stale by definition if >1h old
                verified_at = payload.get("verified_at")
                if verified_at:
                    verified_ts = datetime.fromisoformat(
                        verified_at.replace("Z", "+00:00")
                    )
                    age_hours = (
                        datetime.now(timezone.utc) - verified_ts
                    ).total_seconds() / 3600
                    if age_hours > 1:
                        new_status = "stale"
                else:
                    new_status = "stale"
                verification_source = "time_check"

            elif speed == "never":
                # Immutable facts: mark verified once, never re-check
                new_status = "verified"
                verification_source = "immutable"

            # For slow/fast: we trust that if the memory exists and is recent
            # enough, it's verified. A full file_check would require parsing
            # content for file paths — that's v1.5 territory.
            # For now: mark as verified and update timestamp.
            # This alone is valuable: it creates the verification cycle.

            # Update the point (payload-only, vector preserved)
            updated_payload = {
                **payload,
                "verification_status": new_status,
                "verified_at": now_iso,
                "verification_source": verification_source,
                "access_count": current_access + 1,
                "updated_at": now_iso,
            }

            rowcount = await asyncio.to_thread(
                _set_payload_sync, db, mid, updated_payload
            )

            if rowcount:
                if new_status == "stale":
                    stale_count += 1
                else:
                    verified_count += 1
            else:
                errors.append(f"update failed for {mid}: not found")

        except Exception as e:
            errors.append(f"error for {mid}: {str(e)[:100]}")

    return {
        "verified": verified_count,
        "stale": stale_count,
        "errors": errors[:10],
        "total_processed": verified_count + stale_count,
    }

# Persistent event loop for the API thread.
# asyncio.run() closes the loop after each call — that breaks subsequent calls.
# Instead, we create one loop per thread and reuse it.
_event_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on the thread's persistent event loop."""
    global _event_loop
    if _event_loop is None:
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop.run_until_complete(coro)


def _check_http_token(headers) -> bool:
    """ISO-17: when MEMORY_HTTP_TOKEN is set, X-Memory-Token must match.
    Constant-time compare. Unset env = localhost trust + WARN at startup."""
    expected = os.getenv("MEMORY_HTTP_TOKEN", "")
    if not expected:
        return True
    provided = headers.get("X-Memory-Token", "")
    import hmac as _hmac
    return _hmac.compare_digest(expected, provided)


class _ApiHandler(BaseHTTPRequestHandler):
    """Thin HTTP handler that delegates to MCP tool functions."""

    def do_GET(self) -> None:
        if self.path != "/api/health" and not _check_http_token(self.headers):
            self._json_response(401, {"error": "invalid or missing X-Memory-Token"})
            return
        if self.path == "/api/health":
            self._json_response(200, {
                "status": "ok",
                "endpoints": [
                    "POST /api/ingest-event",
                    "POST /api/heartbeat",
                    "POST /api/heartbeat-dream",
                    "POST /api/save-conversation",
                    "POST /api/consolidate",
                    "POST /api/request-context",
                    "POST /api/verify-memories",
                ],
            })
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not _check_http_token(self.headers):
            self._json_response(401, {"error": "invalid or missing X-Memory-Token"})
            return
        body = self._read_body()
        if body is None:
            return

        try:
            if self.path == "/api/ingest-event" and _ingest_event_fn:
                result = _run_async(_ingest_event_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/heartbeat" and _L0_capture_heartbeat_fn:
                result = _run_async(_L0_capture_heartbeat_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/heartbeat-dream" and _L0_to_L4_consolidation_heartbeat_fn:
                result = _run_async(_L0_to_L4_consolidation_heartbeat_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/save-conversation" and _save_conversation_fn:
                result = _run_async(_save_conversation_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/consolidate" and _consolidate_fn:
                result = _run_async(_consolidate_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/request-context" and _request_context_fn:
                result = _run_async(_request_context_fn(**body))
                self._json_response(200, self._serialize(result))

            elif self.path == "/api/verify-memories":
                result = _run_async(_verify_memories(body))
                self._json_response(200, result)

            else:
                self._json_response(404, {"error": f"not found: {self.path}"})

        except Exception as e:
            logger.warning("API error on %s: %s", self.path, e)
            self._json_response(500, {"error": str(e)})

    def do_OPTIONS(self) -> None:
        """CORS preflight support."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Helpers ──────────────────────────────────────────────────

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw)
        except Exception as e:
            self._json_response(400, {"error": f"invalid body: {e}"})
            return None

    def _json_response(self, code: int, data: Any) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _serialize(self, result: Any) -> Any:
        """Handle Pydantic models, dicts, and plain values."""
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        return {"result": str(result)}

    def log_message(self, format: str, *args: Any) -> None:
        # Silence access logs — too noisy for every tool call
        pass


def start_api_server(
    ingest_event_fn: Callable,
    L0_capture_heartbeat_fn: Callable,
    L0_to_L4_consolidation_heartbeat_fn: Callable,
    save_conversation_fn: Callable,
    consolidate_fn: Callable,
    request_context_fn: Callable | None = None,
    port: int | None = None,
) -> HTTPServer:
    if not os.getenv("MEMORY_HTTP_TOKEN"):
        logger.warning("api_server: MEMORY_HTTP_TOKEN unset — sidecar trusts localhost (ISO-17)")
    """Start the HTTP API server in a background thread.

    Call BEFORE mcp.run(transport="stdio") which blocks the main thread.

    Args:
        ingest_event_fn: L0_capture.ingest_event function
        L0_capture_heartbeat_fn: L0_capture.heartbeat function
        L0_to_L4_consolidation_heartbeat_fn: L0_to_L4_consolidation.heartbeat function
        save_conversation_fn: L2_conversations.save_conversation function
        consolidate_fn: L0_to_L4_consolidation.consolidate function
        request_context_fn: L5_routing.request_context function (optional)
        port: Port to listen on (default: MEMORY_API_PORT env var or 8890)

    Returns:
        The HTTPServer instance (for testing / graceful shutdown).
    """
    global _ingest_event_fn, _L0_capture_heartbeat_fn, _L0_to_L4_consolidation_heartbeat_fn
    global _save_conversation_fn, _consolidate_fn, _request_context_fn

    _ingest_event_fn = ingest_event_fn
    _L0_capture_heartbeat_fn = L0_capture_heartbeat_fn
    _L0_to_L4_consolidation_heartbeat_fn = L0_to_L4_consolidation_heartbeat_fn
    _save_conversation_fn = save_conversation_fn
    _consolidate_fn = consolidate_fn
    _request_context_fn = request_context_fn

    if port is None:
        port = int(os.environ.get("MEMORY_API_PORT") or os.environ.get("AUTOMEM_API_PORT", "8890"))

    server = HTTPServer(("127.0.0.1", port), _ApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="backpack-api")
    thread.start()
    logger.info("Backpack API listening on http://127.0.0.1:%d", port)
    return server
