"""
MCP Observability — Inline instrumentation for all servers.

Usage in any server's main.py:
    from shared.observe import observe, metrics

    @observe("my_tool_name")
    async def my_tool_handler(args):
        ...

Every call is logged to:
  - stdout (real-time)
  - ~/.memory/observe/events-{date}.jsonl (persistent)
  - In-memory metrics (queryable via metrics.get())

Dashboard:
    python3 -m shared.observe --dashboard
    Opens http://127.0.0.1:8080
"""

import time
import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from typing import Any, Callable, Optional

# ── Metrics Store ──────────────────────────────────────────────────

class MetricsStore:
    """Thread-safe in-memory metrics + JSONL logging."""
    def __init__(self):
        self._calls: list[dict] = []
        self._listeners: list[Callable] = []
        self._log_dir = Path(os.getenv("OBSERVE_LOG_DIR", os.path.join(os.getenv("LOG_DIR", "."), "observe")))
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self._log_dir / f"events-{date}.jsonl"

    def emit(self, event: dict):
        event["_ts"] = datetime.now(timezone.utc).isoformat()
        event["_seq"] = len(self._calls)
        self._calls.append(event)

        # Append to JSONL
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass

        # Real-time stdout for CLI visibility
        if event.get("type") == "tool_call":
            status = "❌" if event.get("is_error") else "✅"
            print(f"  [{status}] {event.get('tool','?')}: {event.get('latency_ms', 0):.0f}ms"
                  f" {' | ' + str(event.get('result_preview',''))[:100] if event.get('result_preview') else ''}")
        elif event.get("type") == "error":
            print(f"  🔴 ERROR: {event.get('tool','?')}: {event.get('error','')}")

        # Notify listeners (for dashboard SSE)
        for cb in list(self._listeners):
            try:
                cb(event)
            except Exception:
                pass

    def subscribe(self, cb: Callable):
        self._listeners.append(cb)

    def get(self) -> dict:
        calls = self._calls
        tool_calls = [c for c in calls if c.get("type") == "tool_call"]
        errors = [c for c in tool_calls if c.get("is_error")]
        latencies = [c.get("latency_ms", 0) for c in tool_calls if c.get("latency_ms")]
        latencies_sorted = sorted(latencies) if latencies else [0]

        # Per-tool breakdown
        by_tool: dict[str, dict] = {}
        for tc in tool_calls:
            tool = tc.get("tool", "unknown")
            if tool not in by_tool:
                by_tool[tool] = {"calls": 0, "errors": 0, "latencies": []}
            by_tool[tool]["calls"] += 1
            if tc.get("is_error"):
                by_tool[tool]["errors"] += 1
            if tc.get("latency_ms"):
                by_tool[tool]["latencies"].append(tc["latency_ms"])

        tool_summary = {}
        for name, stats in by_tool.items():
            lats = sorted(stats["latencies"])
            tool_summary[name] = {
                "calls": stats["calls"],
                "errors": stats["errors"],
                "error_rate": round(stats["errors"] / max(stats["calls"], 1) * 100, 1),
                "latency_ms": {
                    "avg": round(sum(lats) / len(lats), 1) if lats else 0,
                    "p50": lats[len(lats)//2] if lats else 0,
                    "p95": lats[int(len(lats)*0.95)] if lats else 0,
                    "p99": lats[int(len(lats)*0.99)] if lats else 0,
                    "min": min(lats) if lats else 0,
                    "max": max(lats) if lats else 0,
                }
            }

        return {
            "summary": {
                "total_tool_calls": len(tool_calls),
                "total_errors": len(errors),
                "error_rate": round(len(errors) / max(len(tool_calls), 1) * 100, 1),
                "total_events": len(calls),
                "uptime_seconds": round(
                    (datetime.now(timezone.utc) - datetime.fromisoformat(calls[0]["_ts"])).total_seconds()
                    if calls else 0
                ),
            },
            "latency_ms": {
                "avg": round(sum(latencies_sorted) / max(len(latencies_sorted), 1), 1),
                "p50": latencies_sorted[len(latencies_sorted)//2] if latencies_sorted else 0,
                "p95": latencies_sorted[int(len(latencies_sorted)*0.95)] if latencies_sorted else 0,
                "p99": latencies_sorted[int(len(latencies_sorted)*0.99)] if latencies_sorted else 0,
            },
            "tools": tool_summary,
            "recent": calls[-100:],
        }

    def reset(self):
        self._calls.clear()


metrics = MetricsStore()


# ── Decorator ──────────────────────────────────────────────────────

def observe(tool_name: str):
    """Wrap any async tool handler with observability."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            # Extract arguments from the MCP tool call convention
            # MCP tools receive ({name, arguments}, context) or just (arguments,)
            tool_args = {}
            if args and isinstance(args[0], dict):
                tool_args = args[0].get("arguments", args[0])
            if kwargs:
                tool_args = kwargs

            try:
                result = await fn(*args, **kwargs)
                latency = (time.monotonic() - start) * 1000

                # Parse result for preview
                result_preview = ""
                is_error = False
                if isinstance(result, str):
                    result_preview = result[:300]
                    try:
                        rdata = json.loads(result)
                        is_error = rdata.get("isError", False)
                        if "content" in rdata:
                            result_preview = rdata["content"][0].get("text", "")[:300]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass
                elif isinstance(result, dict):
                    is_error = result.get("isError", False)
                    if "content" in result:
                        result_preview = result["content"][0].get("text", "")[:300]

                metrics.emit({
                    "type": "tool_call",
                    "tool": tool_name,
                    "args_keys": list(tool_args.keys()) if isinstance(tool_args, dict) else [],
                    "latency_ms": round(latency, 1),
                    "is_error": is_error,
                    "result_preview": result_preview,
                    "status": "error" if is_error else "ok",
                })
                return result

            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                metrics.emit({
                    "type": "error",
                    "tool": tool_name,
                    "args_keys": list(tool_args.keys()) if isinstance(tool_args, dict) else [],
                    "latency_ms": round(latency, 1),
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
                raise

        return wrapper
    return decorator


# ── Dashboard HTTP Server ──────────────────────────────────────────

def run_dashboard(port: int = 8080):
    """Run a simple HTTP dashboard with SSE for real-time updates."""
    import http.server
    import socketserver
    import threading

    clients = []
    lock = threading.Lock()

    def on_event(event):
        data = json.dumps(event, default=str)
        with lock:
            for q in list(clients):
                try:
                    q.put_nowait(data)
                except Exception:
                    pass

    metrics.subscribe(on_event)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q = __import__("queue").Queue()
                with lock:
                    clients.append(q)
                try:
                    # Send initial state
                    init_data = json.dumps({"type": "init", "metrics": metrics.get()}, default=str)
                    self.wfile.write(f"data: {init_data}\n\n".encode())
                    self.wfile.flush()
                    while True:
                        try:
                            data = q.get(timeout=30)
                            self.wfile.write(f"data: {data}\n\n".encode())
                            self.wfile.flush()
                        except __import__("queue").Empty:
                            self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with lock:
                        if q in clients:
                            clients.remove(q)

            elif self.path == "/metrics":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(metrics.get(), default=str).encode())

            elif self.path == "/logs":
                # Return last 500 lines of today's log file
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                try:
                    lines = metrics.log_file.read_text().strip().split("\n")
                    self.wfile.write("\n".join(lines[-500:]).encode())
                except FileNotFoundError:
                    self.wfile.write(b"No logs yet")

            elif self.path in ("/", "/dashboard"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())

            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Silence access logs

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("", port), Handler) as httpd:
        print(f"  📊 Dashboard: http://127.0.0.1:{port}")
        print(f"  📡 SSE events:  http://127.0.0.1:{port}/events")
        print(f"  📋 Metrics JSON: http://127.0.0.1:{port}/metrics")
        print(f"  📄 Raw logs:    http://127.0.0.1:{port}/logs")
        httpd.serve_forever()


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>MCP Memory — Live Observability</title>
<meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'SF Mono','Fira Code','Cascadia Code',monospace;background:#06060c;color:#d4d4d8;padding:0}
header{background:#0c0c16;border-bottom:1px solid #1a1a2e;padding:16px 24px;display:flex;align-items:center;gap:16px}
header h1{font-size:1.1em;color:#8b5cf6}
header .status{font-size:.75em;color:#4ade80;background:#0a2e1a;padding:4px 10px;border-radius:4px}
header .reset{margin-left:auto;background:#1a1a2e;border:1px solid #2a2a3e;color:#888;padding:6px 12px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:.75em}
header .reset:hover{border-color:#8b5cf6;color:#8b5cf6}
main{padding:20px 24px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:24px}
.m{background:#0c0c16;border:1px solid #1a1a2e;border-radius:6px;padding:14px}
.m .l{color:#555;font-size:.65em;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.m .v{font-size:1.6em;font-weight:700}
.m .v.g{color:#4ade80}.m .v.r{color:#f87171}.m .v.y{color:#fbbf24}.m .v.b{color:#60a5fa}.m .v.p{color:#a78bfa}
h2{color:#a78bfa;font-size:.85em;margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid #1a1a2e}
table{width:100%;border-collapse:collapse;font-size:.75em}
th{text-align:left;color:#555;padding:6px 8px;border-bottom:1px solid #1a1a2e;font-weight:500}
td{padding:5px 8px;border-bottom:1px solid #0e0e18;vertical-align:top}
tr:hover{background:#0e0e18}
.tn{color:#8b5cf6}.lat{color:#4ade80}.err{color:#f87171}.prev{color:#666;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px}
.dot.g{background:#4ade80}.dot.r{background:#f87171}.dot.b{background:#60a5fa}
.tools-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-bottom:24px}
.tool-card{background:#0c0c16;border:1px solid #1a1a2e;border-radius:6px;padding:12px}
.tool-card .name{color:#8b5cf6;font-size:.85em;margin-bottom:6px}
.tool-card .stats{display:flex;gap:12px;font-size:.7em;color:#888}
.tool-card .stats span{display:flex;align-items:center;gap:4px}
#events{max-height:450px;overflow-y:auto;scroll-behavior:smooth}
#events::-webkit-scrollbar{width:6px}
#events::-webkit-scrollbar-thumb{background:#1a1a2e;border-radius:3px}
</style></head><body>
<header>
  <h1>🔌 MCP Memory Server — Observability Dashboard</h1>
  <div class="status" id="status">● connecting</div>
  <button class="reset" onclick="fetch('/reset',{{method:'POST'}})">Reset Metrics</button>
</header>
<main>
  <div class="metrics" id="metrics"></div>
  <h2>Tool Breakdown</h2>
  <div class="tools-grid" id="tools"></div>
  <h2>Live Event Stream</h2>
  <table><thead><tr>
    <th style="width:70px">Time</th><th style="width:50px">Type</th>
    <th style="width:200px">Tool</th><th style="width:70px">Latency</th>
    <th style="width:50px">Status</th><th>Preview</th>
  </tr></thead><tbody id="events"></tbody></table>
</main>
<script>
const source = new EventSource('/events');
let seq = 0;
source.onopen = () => {{
  document.getElementById('status').textContent = '● live';
  document.getElementById('status').style.color = '#4ade80';
}};
source.onerror = () => {{
  document.getElementById('status').textContent = '● disconnected';
  document.getElementById('status').style.color = '#f87171';
}};
source.onmessage = (e) => {{
  const d = JSON.parse(e.data);
  if (d.type === 'init') {{ render(d.metrics); return; }}
  seq++;
  addEvent(d);
}};
function render(m) {{
  const s = m.summary;
  const l = m.latency_ms;
  document.getElementById('metrics').innerHTML = `
    <div class="m"><div class="l">Tool Calls</div><div class="v b">${{s.total_tool_calls}}</div></div>
    <div class="m"><div class="l">Errors</div><div class="v ${{s.total_errors > 0 ? 'r' : 'g'}}">${{s.total_errors}}</div></div>
    <div class="m"><div class="l">Error Rate</div><div class="v ${{s.error_rate > 5 ? 'r' : 'g'}}">${{s.error_rate}}%</div></div>
    <div class="m"><div class="l">Avg Latency</div><div class="v g">${{l.avg.toFixed(0)}}ms</div></div>
    <div class="m"><div class="l">P50 Latency</div><div class="v b">${{l.p50}}ms</div></div>
    <div class="m"><div class="l">P95 Latency</div><div class="v y">${{l.p95}}ms</div></div>
    <div class="m"><div class="l">P99 Latency</div><div class="v r">${{l.p99}}ms</div></div>
    <div class="m"><div class="l">Total Events</div><div class="v p">${{m.total_events}}</div></div>
  `;
  let thtml = '';
  for (const [name, st] of Object.entries(m.tools || {{}}).sort((a,b) => b[1].calls - a[1].calls)) {{
    const la = st.latency_ms;
    const er = st.error_rate;
    thtml += `<div class="tool-card">
      <div class="name">${{name}}</div>
      <div class="stats">
        <span>📞 ${{st.calls}} calls</span>
        <span class="${{er > 5 ? 'err' : ''}}">❌ ${{er}}%</span>
        <span class="lat">⏱ ${{la.avg}}ms avg</span>
        <span class="lat">P95: ${{la.p95}}ms</span>
      </div>
    </div>`;
  }}
  document.getElementById('tools').innerHTML = thtml || '<div style="color:#555;padding:20px">No tool calls yet</div>';
}}
function addEvent(d) {{
  const tb = document.getElementById('events');
  const tr = document.createElement('tr');
  const t = new Date(d._ts || d.ts).toLocaleTimeString();
  if (d.type === 'tool_call') {{
    const dot = d.is_error ? 'r' : 'g';
    const cls = d.is_error ? 'err' : '';
    tr.className = cls;
    tr.innerHTML = `<td>${{t}}</td><td><span class="dot ${{dot}}"></span>tool</td>
      <td class="tn">${{d.tool}}</td><td class="lat">${{d.latency_ms}}ms</td>
      <td>${{d.is_error ? '❌' : '✅'}}</td><td class="prev">${{(d.result_preview||'').substring(0,120)}}</td>`;
  }} else if (d.type === 'error') {{
    tr.className = 'err';
    tr.innerHTML = `<td>${{t}}</td><td><span class="dot r"></span>error</td>
      <td class="tn">${{d.tool}}</td><td class="lat">${{d.latency_ms}}ms</td>
      <td>🔴</td><td class="prev">${{(d.error||'').substring(0,120)}}</td>`;
  }} else {{
    tr.innerHTML = `<td>${{t}}</td><td><span class="dot b"></span>rpc</td>
      <td class="tn">${{d.method||d.type||'?'}}</td><td class="lat">${{d.latency_ms||0}}ms</td>
      <td>ℹ️</td><td></td>`;
  }}
  tb.insertBefore(tr, tb.firstChild);
  while (tb.children.length > 500) tb.removeChild(tb.lastChild);
}}
</script></body></html>"""


# ── CLI entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", action="store_true", help="Run dashboard only")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log", help="Show last N log entries")
    args = parser.parse_args()

    if args.log:
        try:
            lines = metrics.log_file.read_text().strip().split("\n")
            for line in lines[-int(args.log):]:
                print(json.loads(line))
        except FileNotFoundError:
            print("No logs found yet.")
    elif args.dashboard:
        run_dashboard(args.port)
    else:
        print("Usage:")
        print("  python3 -m shared.observe --dashboard       # Start dashboard")
        print("  python3 -m shared.observe --log 50          # Show last 50 events")
        print("  python3 -m shared.observe --port 9090       # Custom port")
