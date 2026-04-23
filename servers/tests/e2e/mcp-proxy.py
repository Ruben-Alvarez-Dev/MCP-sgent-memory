#!/usr/bin/env python3
"""
MCP Forensic Proxy
==================
Transparent proxy between any MCP client and the real gateway.
Zero modification to existing servers.

Features:
  - Timestamps: µs precision (Unix epoch + ISO 8601)
  - Full payloads: request args + complete response captured
  - Trace IDs: unique per request, links request→response→error
  - Correlation: session_id + trace_id for forensic chain
  - JSONL log: append-only, one event per line, machine-parseable
  - SSE broadcast: real-time events to dashboard + external consumers
  - Metrics: per-tool call count, latency (avg/p50/p95/p99), error rate

Usage:
  python3 mcp-proxy.py --upstream http://127.0.0.1:3050 --port 3051

  Dashboard:  http://127.0.0.1:8080
  SSE events: http://127.0.0.1:8080/events
  Metrics:    http://127.0.0.1:8080/metrics
  Raw logs:   http://127.0.0.1:8080/logs
"""

import asyncio
import json
import time
import uuid
import hashlib
import argparse
import sys
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ═══════════════════════════════════════════════════════════════════
# TRACE ID GENERATOR
# ═══════════════════════════════════════════════════════════════════

def gen_trace_id() -> str:
    """Generate a forensic-grade trace ID (UUID v4 + short hash)."""
    uid = uuid.uuid4().hex
    ts = str(time.time_ns())
    short = hashlib.sha256(f"{uid}:{ts}".encode()).hexdigest()[:8]
    return f"trc-{uid[:12]}-{short}"


def gen_span_id() -> str:
    """Generate a span ID for sub-operations."""
    return uuid.uuid4().hex[:16]


def precise_ts() -> str:
    """ISO 8601 with µs precision + timezone."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def epoch_us() -> int:
    """Unix epoch in microseconds."""
    return time.time_ns() // 1000


# ═══════════════════════════════════════════════════════════════════
# EVENT STORE + BROADCAST
# ═══════════════════════════════════════════════════════════════════

class EventStore:
    """Append-only event store with SSE broadcast + JSONL persistence."""

    def __init__(self, log_dir: str = "~/.memory/observe"):
        self._path = Path(os.path.expanduser(log_dir))
        self._path.mkdir(parents=True, exist_ok=True)
        self._clients: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

        # In-memory index for fast queries
        self._events: list[dict] = []
        self._by_trace: dict[str, list[dict]] = {}
        self._by_tool: dict[str, list[dict]] = {}
        self._by_session: dict[str, list[dict]] = {}

    @property
    def today_file(self) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self._path / f"trace-{date}.jsonl"

    async def emit(self, event: dict):
        """Emit an event: persist, index, broadcast."""
        # Enrich with forensic markers
        event["event_seq"] = len(self._events)
        if "_ts_iso" not in event:
            event["_ts_iso"] = precise_ts()
        if "_ts_epoch_us" not in event:
            event["_ts_epoch_us"] = epoch_us()

        # Index
        async with self._lock:
            self._events.append(event)

            trace_id = event.get("trace_id")
            if trace_id:
                self._by_trace.setdefault(trace_id, []).append(event)

            tool = event.get("tool")
            if tool:
                self._by_tool.setdefault(tool, []).append(event)

            session = event.get("session_id")
            if session:
                self._by_session.setdefault(session, []).append(event)

            # Keep last 10000 in memory
            if len(self._events) > 10000:
                self._events = self._events[-8000:]

        # Persist to JSONL (fire and forget — non-blocking)
        asyncio.create_task(self._persist(event))

        # Broadcast to SSE clients
        data = json.dumps(event, default=str)
        for q in list(self._clients):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def _persist(self, event: dict):
        try:
            with open(self.today_file, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as e:
            sys.stderr.write(f"[proxy] log write failed: {e}\n")

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._clients:
            self._clients.remove(q)

    def get_metrics(self) -> dict:
        """Compute aggregate metrics from in-memory index."""
        tool_calls = [e for e in self._events if e.get("event_type") == "tool_call"]
        errors = [e for e in tool_calls if e.get("is_error")]
        latencies = sorted([e.get("latency_ms", 0) for e in tool_calls if e.get("latency_ms") is not None])

        # Per-tool
        by_tool: dict[str, dict] = {}
        for tc in tool_calls:
            t = tc.get("tool", "unknown")
            if t not in by_tool:
                by_tool[t] = {"calls": 0, "errors": 0, "latencies": []}
            by_tool[t]["calls"] += 1
            if tc.get("is_error"):
                by_tool[t]["errors"] += 1
            if tc.get("latency_ms") is not None:
                by_tool[t]["latencies"].append(tc["latency_ms"])

        tool_summary = {}
        for name, s in by_tool.items():
            lats = sorted(s["latencies"])
            n = len(lats)
            tool_summary[name] = {
                "calls": s["calls"],
                "errors": s["errors"],
                "error_rate_pct": round(s["errors"] / max(s["calls"], 1) * 100, 2),
                "latency_ms": {
                    "min": lats[0] if lats else 0,
                    "max": lats[-1] if lats else 0,
                    "avg": round(sum(lats) / n, 2) if n else 0,
                    "p50": lats[n // 2] if n else 0,
                    "p90": lats[int(n * 0.9)] if n else 0,
                    "p95": lats[int(n * 0.95)] if n else 0,
                    "p99": lats[int(n * 0.99)] if n else 0,
                }
            }

        first_ts = self._events[0].get("_ts_iso") if self._events else None
        last_ts = self._events[-1].get("_ts_iso") if self._events else None

        return {
            "summary": {
                "total_events": len(self._events),
                "total_tool_calls": len(tool_calls),
                "total_errors": len(errors),
                "error_rate_pct": round(len(errors) / max(len(tool_calls), 1) * 100, 2),
                "tools_registered": len(by_tool),
                "sessions_active": len(self._by_session),
                "first_event": first_ts,
                "last_event": last_ts,
            },
            "latency_ms": {
                "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0,
                "p50": latencies[len(latencies) // 2] if latencies else 0,
                "p90": latencies[int(len(latencies) * 0.9)] if latencies else 0,
                "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
                "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
            },
            "tools": tool_summary,
            "recent_events": self._events[-200:],
        }

    def get_trace(self, trace_id: str) -> list[dict]:
        """Get full forensic chain for a trace ID."""
        return self._by_trace.get(trace_id, [])

    def get_tool_events(self, tool: str) -> list[dict]:
        return self._by_tool.get(tool, [])


# ═══════════════════════════════════════════════════════════════════
# FORENSIC PROXY
# ═══════════════════════════════════════════════════════════════════

class ForensicProxy:
    """
    HTTP proxy that intercepts MCP JSON-RPC traffic.

    For every request:
      1. Generates trace_id + span_id
      2. Records full request payload (method, params, headers)
      3. Forwards to upstream
      4. Records full response (status, headers, body)
      5. Computes latency (µs precision)
      6. Emits structured event with all forensic markers
    """

    def __init__(self, upstream: str, port: int, store: EventStore):
        self.upstream = upstream.rstrip("/")
        self.port = port
        self.store = store

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single TCP connection from an MCP client."""
        try:
            request_line_bytes = await asyncio.wait_for(reader.readline(), timeout=30)
            if not request_line_bytes:
                return
            request_line = request_line_bytes.decode("utf-8", errors="replace").strip()

            # Parse HTTP headers
            headers: dict[str, str] = {}
            content_length = 0
            while True:
                line_bytes = await asyncio.wait_for(reader.readline(), timeout=10)
                if line_bytes in (b"\r\n", b"\n", b""):
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip().lower()
                    headers[k] = val.strip()
                    if k == "content-length":
                        content_length = int(val.strip())

            if request_line.startswith("GET"):
                await self._handle_get(request_line, headers, reader, writer)
            elif request_line.startswith("POST"):
                await self._handle_post(request_line, headers, content_length, reader, writer)
            else:
                writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                await writer.drain()

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            trace_id = gen_trace_id()
            await self.store.emit({
                "event_type": "proxy_error",
                "trace_id": trace_id,
                "span_id": gen_span_id(),
                "error": str(e),
                "error_class": type(e).__name__,
            })
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_get(self, request_line: str, headers: dict, reader, writer):
        """Handle GET — SSE event stream or forward to upstream SSE."""
        session_id = headers.get("mcp-session-id", "")

        if "/events" in request_line:
            # Dashboard/external consumer SSE subscription
            self._write_sse_headers(writer)
            await writer.drain()

            q = self.store.subscribe()
            try:
                # Send initial state
                metrics = self.store.get_metrics()
                init = json.dumps({"event_type": "proxy_init", "metrics": metrics})
                writer.write(f"data: {init}\n\n".encode())
                await writer.drain()

                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=30)
                        writer.write(f"data: {data}\n\n".encode())
                        await writer.drain()
                    except asyncio.TimeoutError:
                        writer.write(b": heartbeat\n\n")
                        await writer.drain()
            finally:
                self.store.unsubscribe(q)

        elif "/metrics" in request_line:
            metrics = self.store.get_metrics()
            body = json.dumps(metrics, default=str, indent=2).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n")
            writer.write(body)
            await writer.drain()

        elif "/logs" in request_line:
            try:
                lines = self.store.today_file.read_text().strip().split("\n")
                body = "\n".join(lines[-1000:]).encode()
            except FileNotFoundError:
                body = b"No logs yet"
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n")
            writer.write(body)
            await writer.drain()

        elif "/traces" in request_line:
            # Query: /traces?trace_id=xxx
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(request_line.split(" ", 1)[1] if " " in request_line else "")
            params = parse_qs(parsed.query)
            tid = params.get("trace_id", [None])[0]
            if tid:
                events = self.store.get_trace(tid)
                body = json.dumps({"trace_id": tid, "events": events}, default=str, indent=2).encode()
            else:
                body = json.dumps({"error": "missing trace_id param"}, indent=2).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
            writer.write(body)
            await writer.drain()

        elif "/dashboard" in request_line or request_line.startswith("GET / ") or request_line.startswith("GET / HTTP"):
            body = DASHBOARD_HTML.encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n")
            writer.write(body)
            await writer.drain()

        else:
            # Forward SSE from upstream to client
            await self._forward_upstream_sse(session_id, headers, writer)

    async def _forward_upstream_sse(self, session_id: str, client_headers: dict, writer):
        """Proxy SSE stream from upstream gateway to client."""
        import urllib.request
        url = f"{self.upstream}/mcp"
        req = urllib.request.Request(url, headers={
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            **({"Mcp-Session-Id": session_id} if session_id else {}),
        })
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            resp_headers = dict(resp.headers)
            resp_session = resp_headers.get("Mcp-Session-Id", session_id)

            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n")
            if resp_session:
                writer.write(f"Mcp-Session-Id: {resp_session}\r\n".encode())
            writer.write(b"Connection: keep-alive\r\n\r\n")
            await writer.drain()

            trace_id = gen_trace_id()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()

                await self.store.emit({
                    "event_type": "sse_forward",
                    "trace_id": trace_id,
                    "span_id": gen_span_id(),
                    "session_id": resp_session,
                    "bytes_forwarded": len(chunk),
                })
        except Exception as e:
            writer.write(f"HTTP/1.1 502 Bad Gateway\r\n\r\nUpstream error: {e}".encode())
            await writer.drain()

    async def _handle_post(self, request_line: str, headers: dict, content_length: int, reader, writer):
        """Handle POST JSON-RPC — the main MCP traffic."""
        # Read body
        body = b""
        remaining = content_length
        while remaining > 0:
            chunk = await asyncio.wait_for(reader.read(min(remaining, 65536)), timeout=10)
            if not chunk:
                break
            body += chunk
            remaining -= len(chunk)

        session_id = headers.get("mcp-session-id", "")
        request_start_epoch_us = epoch_us()
        request_start_iso = precise_ts()

        # Parse request
        try:
            request_json = json.loads(body)
        except json.JSONDecodeError:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\n\r\n")
            writer.write(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}).encode())
            await writer.drain()
            await self.store.emit({
                "event_type": "parse_error",
                "trace_id": gen_trace_id(),
                "span_id": gen_span_id(),
                "session_id": session_id,
            })
            return

        # Generate forensic markers
        trace_id = gen_trace_id()
        span_id = gen_span_id()
        req_id = request_json.get("id")
        method = request_json.get("method", "unknown")

        # Detect tool calls
        is_tool_call = method == "tools/call"
        tool_name = None
        tool_args = None
        if is_tool_call:
            params = request_json.get("params", {})
            tool_name = params.get("name", "unknown")
            tool_args = params.get("arguments", {})

        # Forward to upstream
        upstream_start = time.monotonic()
        try:
            req = urllib.request.Request(
                f"{self.upstream}/mcp",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    **({"Mcp-Session-Id": session_id} if session_id else {}),
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_status = resp.status
                resp_reason = resp.reason
                resp_headers = dict(resp.headers)
                resp_session = resp_headers.get("Mcp-Session-Id", session_id)
                resp_body = resp.read()

                latency_ms = (time.monotonic() - upstream_start) * 1000

                # Build HTTP response to client
                resp_headers_str = ""
                for k, v in resp_headers.items():
                    resp_headers_str += f"{k}: {v}\r\n"

                writer.write(f"HTTP/1.1 {resp_status} {resp_reason}\r\n".encode())
                writer.write(resp_headers_str.encode())
                writer.write(b"\r\n")
                writer.write(resp_body)
                await writer.drain()

                # Parse response for forensic event
                response_preview = ""
                is_error = False
                error_detail = None

                try:
                    resp_parsed = json.loads(resp_body.decode())
                    if "error" in resp_parsed:
                        is_error = True
                        err = resp_parsed["error"]
                        error_detail = f"code={err.get('code')}: {err.get('message', '')}"
                    elif "result" in resp_parsed:
                        result = resp_parsed["result"]
                        if isinstance(result, dict) and "content" in result:
                            content = result["content"]
                            if content and isinstance(content, list):
                                response_preview = content[0].get("text", "")[:500]
                            is_error = result.get("isError", False)
                except Exception:
                    response_preview = resp_body.decode("utf-8", errors="replace")[:500]

                if is_tool_call:
                    await self.store.emit({
                        "event_type": "tool_call",
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "request_id": req_id,
                        "session_id": session_id,
                        "upstream_session_id": resp_session,
                        "tool": tool_name,
                        "tool_args": tool_args,
                        "request_ts_iso": request_start_iso,
                        "request_ts_epoch_us": request_start_epoch_us,
                        "response_ts_iso": precise_ts(),
                        "response_ts_epoch_us": epoch_us(),
                        "latency_ms": round(latency_ms, 3),
                        "latency_us": round(latency_ms * 1000, 0),
                        "is_error": is_error,
                        "error_detail": error_detail,
                        "response_status": resp_status,
                        "response_preview": response_preview,
                        "request_payload_size": len(body),
                        "response_payload_size": len(resp_body),
                    })
                else:
                    await self.store.emit({
                        "event_type": "rpc_call",
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "request_id": req_id,
                        "session_id": session_id,
                        "upstream_session_id": resp_session,
                        "method": method,
                        "request_ts_iso": request_start_iso,
                        "request_ts_epoch_us": request_start_epoch_us,
                        "response_ts_iso": precise_ts(),
                        "response_ts_epoch_us": epoch_us(),
                        "latency_ms": round(latency_ms, 3),
                        "response_status": resp_status,
                        "request_payload_size": len(body),
                        "response_payload_size": len(resp_body),
                    })

        except urllib.error.HTTPError as e:
            latency_ms = (time.monotonic() - upstream_start) * 1000
            error_body = e.read().decode("utf-8", errors="replace")

            writer.write(f"HTTP/1.1 {e.code} {e.reason}\r\nContent-Type: application/json\r\n\r\n".encode())
            writer.write(error_body.encode())
            await writer.drain()

            if is_tool_call:
                await self.store.emit({
                    "event_type": "tool_call",
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "request_id": req_id,
                    "session_id": session_id,
                    "tool": tool_name,
                    "tool_args": tool_args,
                    "request_ts_iso": request_start_iso,
                    "request_ts_epoch_us": request_start_epoch_us,
                    "response_ts_iso": precise_ts(),
                    "response_ts_epoch_us": epoch_us(),
                    "latency_ms": round(latency_ms, 3),
                    "is_error": True,
                    "error_detail": f"HTTP {e.code} {e.reason}: {error_body[:300]}",
                    "response_status": e.code,
                })

        except Exception as e:
            latency_ms = (time.monotonic() - upstream_start) * 1000

            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: application/json\r\n\r\n")
            err_json = json.dumps({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": req_id})
            writer.write(err_json.encode())
            await writer.drain()

            if is_tool_call:
                await self.store.emit({
                    "event_type": "tool_call",
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "request_id": req_id,
                    "session_id": session_id,
                    "tool": tool_name,
                    "tool_args": tool_args,
                    "request_ts_iso": request_start_iso,
                    "request_ts_epoch_us": request_start_epoch_us,
                    "response_ts_iso": precise_ts(),
                    "response_ts_epoch_us": epoch_us(),
                    "latency_ms": round(latency_ms, 3),
                    "is_error": True,
                    "error_detail": f"Proxy error: {type(e).__name__}: {e}",
                })


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD HTML
# ═══════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html><head><title>MCP Forensic Dashboard</title>
<meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono','Fira Code',monospace;background:#06060c;color:#d4d4d8}
header{background:#0c0c16;border-bottom:1px solid #1a1a2e;padding:12px 20px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:100}
header h1{font-size:1em;color:#8b5cf6}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.status-dot.live{background:#4ade80;box-shadow:0 0 6px #4ade80}
.status-dot.dead{background:#f87171}
#status-text{font-size:.7em;color:#888}
main{padding:16px 20px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:20px}
.m{background:#0c0c16;border:1px solid #1a1a2e;border-radius:4px;padding:12px}
.m .l{color:#555;font-size:.6em;text-transform:uppercase;letter-spacing:.5px}
.m .v{font-size:1.5em;font-weight:700}
.m .g{color:#4ade80}.m .r{color:#f87171}.m .y{color:#fbbf24}.m .b{color:#60a5fa}.m .p{color:#a78bfa}
h2{color:#a78bfa;font-size:.75em;margin:16px 0 8px;padding-bottom:4px;border-bottom:1px solid #1a1a2e}
table{width:100%;border-collapse:collapse;font-size:.7em}
th{text-align:left;color:#555;padding:5px 6px;border-bottom:1px solid #1a1a2e;font-weight:400}
td{padding:4px 6px;border-bottom:1px solid #0e0e18;vertical-align:top;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover{background:#0e0e18}
.tn{color:#8b5cf6}.lat{color:#4ade80}.err{color:#f87171}
.dot{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:4px}
.dot.g{background:#4ade80}.dot.r{background:#f87171}.dot.b{background:#60a5fa}
.trace-id{font-size:.6em;color:#666;cursor:pointer}
.trace-id:hover{color:#8b5cf6}
#events{max-height:500px;overflow-y:auto}
#events::-webkit-scrollbar{width:4px}
#events::-webkit-scrollbar-thumb{background:#1a1a2e;border-radius:2px}
.tools-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin-bottom:16px}
.tc{background:#0c0c16;border:1px solid #1a1a2e;border-radius:4px;padding:10px}
.tc .n{color:#8b5cf6;font-size:.8em;margin-bottom:4px}
.tc .s{font-size:.65em;color:#888;display:flex;gap:10px}
</style></head><body>
<header>
  <h1>🔍 MCP Forensic Proxy</h1>
  <span class="status-dot dead" id="dot"></span>
  <span id="status-text">connecting...</span>
</header>
<main>
  <div class="metrics" id="metrics"></div>
  <h2>Tool Breakdown</h2>
  <div class="tools-grid" id="tools"></div>
  <h2>Forensic Event Log</h2>
  <table><thead><tr>
    <th style="width:60px">Time</th><th style="width:40px"></th>
    <th style="width:180px">Tool / Method</th><th style="width:65px">Latency</th>
    <th style="width:45px">Status</th><th>Trace ID</th><th>Preview</th>
  </tr></thead><tbody id="events"></tbody></table>
</main>
<script>
const source = new EventSource('/events');
source.onopen = () => {
  document.getElementById('dot').className = 'status-dot live';
  document.getElementById('status-text').textContent = 'live';
  document.getElementById('status-text').style.color = '#4ade80';
};
source.onerror = () => {
  document.getElementById('dot').className = 'status-dot dead';
  document.getElementById('status-text').textContent = 'disconnected';
  document.getElementById('status-text').style.color = '#f87171';
};
source.onmessage = (e) => {
  const d = JSON.parse(e.data);
  if (d.type === 'proxy_init' || d.event_type === 'proxy_init') { render(d.metrics || d); return; }
  addEvent(d);
};
function render(m) {
  const s = (m.summary || {});
  const l = (m.latency_ms || {});
  document.getElementById('metrics').innerHTML = `
    <div class="m"><div class="l">Tool Calls</div><div class="v b">${s.total_tool_calls||0}</div></div>
    <div class="m"><div class="l">Errors</div><div class="v ${s.total_errors>0?'r':'g'}">${s.total_errors||0}</div></div>
    <div class="m"><div class="l">Error Rate</div><div class="v ${s.error_rate_pct>5?'r':'g'}">${s.error_rate_pct||0}%</div></div>
    <div class="m"><div class="l">Avg Latency</div><div class="v g">${l.avg||0}ms</div></div>
    <div class="m"><div class="l">P50</div><div class="v b">${l.p50||0}ms</div></div>
    <div class="m"><div class="l">P95</div><div class="v y">${l.p95||0}ms</div></div>
    <div class="m"><div class="l">P99</div><div class="v r">${l.p99||0}ms</div></div>
    <div class="m"><div class="l">Events</div><div class="v p">${s.total_events||0}</div></div>
  `;
  const tools = m.tools || {};
  let th = '';
  for (const [n, st] of Object.entries(tools).sort((a,b)=>b[1].calls-a[1].calls)) {
    const la = st.latency_ms || {};
    th += `<div class="tc"><div class="n">${n}</div><div class="s">
      <span>📞 ${st.calls}</span><span class="${st.error_rate_pct>5?'err':''}">❌ ${st.error_rate_pct}%</span>
      <span class="lat">⏱ ${la.avg}ms</span><span class="lat">P95: ${la.p95}ms</span>
    </div></div>`;
  }
  document.getElementById('tools').innerHTML = th || '<div style="color:#555;padding:16px">No tool calls yet</div>';
}
function addEvent(d) {
  const tb = document.getElementById('events');
  const tr = document.createElement('tr');
  const t = new Date(d._ts_iso || d._ts || '').toLocaleTimeString();
  if (d.event_type === 'tool_call') {
    const dot = d.is_error ? 'r' : 'g';
    tr.className = d.is_error ? 'err' : '';
    tr.innerHTML = `<td>${t}</td><td><span class="dot ${dot}"></span></td>
      <td class="tn">${d.tool||'?'}</td><td class="lat">${d.latency_ms||0}ms</td>
      <td>${d.is_error?'❌':'✅'}</td>
      <td><span class="trace-id" onclick="fetch('/traces?trace_id=${d.trace_id}').then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">${(d.trace_id||'').substring(0,20)}…</span></td>
      <td>${(d.response_preview||'').substring(0,100)}</td>`;
  } else if (d.event_type === 'rpc_call') {
    tr.innerHTML = `<td>${t}</td><td><span class="dot b"></span></td>
      <td class="tn">${d.method||'?'}</td><td class="lat">${d.latency_ms||0}ms</td>
      <td>ℹ️</td>
      <td><span class="trace-id">${(d.trace_id||'').substring(0,20)}…</span></td><td></td>`;
  } else if (d.event_type === 'proxy_error' || d.event_type === 'tool_error') {
    tr.className = 'err';
    tr.innerHTML = `<td>${t}</td><td><span class="dot r"></span></td>
      <td class="tn">${d.tool||d.event_type}</td><td class="lat">${d.latency_ms||0}ms</td>
      <td>🔴</td><td><span class="trace-id">${(d.trace_id||'').substring(0,20)}…</span></td>
      <td>${(d.error_detail||d.error||'').substring(0,100)}</td>`;
  } else {
    tr.innerHTML = `<td>${t}</td><td><span class="dot b"></span></td>
      <td class="tn">${d.event_type||'?'}</td><td></td><td></td><td></td><td></td>`;
  }
  tb.insertBefore(tr, tb.firstChild);
  while (tb.children.length > 500) tb.removeChild(tb.lastChild);
}
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="MCP Forensic Proxy")
    parser.add_argument("--upstream", default="http://127.0.0.1:3050",
                        help="Upstream MCP gateway URL (default: http://127.0.0.1:3050)")
    parser.add_argument("--port", type=int, default=3051,
                        help="Proxy listen port (default: 3051)")
    parser.add_argument("--dashboard-port", type=int, default=8080,
                        help="Dashboard HTTP port (default: 8080)")
    parser.add_argument("--log-dir", default="~/.memory/observe",
                        help="JSONL log directory")
    args = parser.parse_args()

    store = EventStore(log_dir=args.log_dir)
    proxy = ForensicProxy(args.upstream, args.port, store)

    # Start proxy server (MCP traffic)
    proxy_server = await asyncio.start_server(proxy.handle_client, "0.0.0.0", args.port)

    # Start dashboard server (HTTP + SSE)
    async def dashboard_handler(reader, writer):
        """Route HTTP requests to appropriate handlers."""
        try:
            req_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not req_line:
                return
            req_str = req_line.decode("utf-8", errors="replace").strip()

            # Parse headers
            headers = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
                if b":" in line:
                    k, v = line.decode("utf-8", errors="replace").split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if req_str.startswith("GET"):
                if "/events" in req_str:
                    # SSE
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nConnection: keep-alive\r\n\r\n")
                    await writer.drain()
                    q = store.subscribe()
                    try:
                        init_data = json.dumps({"event_type": "proxy_init", "metrics": store.get_metrics()}, default=str)
                        writer.write(f"data: {init_data}\n\n".encode())
                        await writer.drain()
                        while True:
                            try:
                                data = await asyncio.wait_for(q.get(), timeout=30)
                                writer.write(f"data: {data}\n\n".encode())
                                await writer.drain()
                            except asyncio.TimeoutError:
                                writer.write(b": heartbeat\n\n")
                                await writer.drain()
                    finally:
                        store.unsubscribe(q)

                elif "/metrics" in req_str:
                    body = json.dumps(store.get_metrics(), default=str, indent=2).encode()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n")
                    writer.write(body)
                    await writer.drain()

                elif "/logs" in req_str:
                    try:
                        lines = store.today_file.read_text().strip().split("\n")
                        body = "\n".join(lines[-1000:]).encode()
                    except FileNotFoundError:
                        body = b"No logs yet"
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n")
                    writer.write(body)
                    await writer.drain()

                elif "/traces" in req_str:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(req_str.split(" ", 1)[1] if " " in req_str else "")
                    params = parse_qs(parsed.query)
                    tid = params.get("trace_id", [None])[0]
                    if tid:
                        events = store.get_trace(tid)
                        body = json.dumps({"trace_id": tid, "events": events}, default=str, indent=2).encode()
                    else:
                        body = json.dumps({"error": "missing trace_id param"}, indent=2).encode()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
                    writer.write(body)
                    await writer.drain()

                else:
                    body = DASHBOARD_HTML.encode()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n")
                    writer.write(body)
                    await writer.drain()

            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
                await writer.drain()

        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    dash_server = await asyncio.start_server(dashboard_handler, "0.0.0.0", args.dashboard_port)

    print(f"╔══════════════════════════════════════════════════════════╗")
    print(f"║   MCP Forensic Proxy                                     ║")
    print(f"╠══════════════════════════════════════════════════════════╣")
    print(f"║  Proxy:       0.0.0.0:{args.port}")
    print(f"║  Upstream:    {args.upstream}")
    print(f"║  Dashboard:   http://127.0.0.1:{args.dashboard_port}")
    print(f"║  SSE Events:  http://127.0.0.1:{args.dashboard_port}/events")
    print(f"║  Metrics API: http://127.0.0.1:{args.dashboard_port}/metrics")
    print(f"║  Trace Query: http://127.0.0.1:{args.dashboard_port}/traces?trace_id=xxx")
    print(f"║  Raw Logs:    http://127.0.0.1:{args.dashboard_port}/logs")
    print(f"║  Log File:    {store.today_file}")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print(f"")
    print(f"  → Point MCP client to: http://127.0.0.1:{args.port}/mcp")
    print(f"  → Open dashboard at:   http://127.0.0.1:{args.dashboard_port}")
    print(f"")

    async with proxy_server:
        async with dash_server:
            await asyncio.gather(
                proxy_server.serve_forever(),
                dash_server.serve_forever(),
            )


if __name__ == "__main__":
    asyncio.run(main())
