"""Lightweight tool-usage telemetry (E2E audit follow-up, 2026-09-07).

Answers "is the memory actually used?" — one JSONL line per MCP tool call:
    {"ts": <epoch>, "tool": <name>, "ms": <latency>, "ok": <bool>}

No content is ever recorded — only tool name, latency and outcome.
Appends to `<data>/metrics/usage.jsonl`; aggregated across all client
instances (they share the same data dir). Telemetry must NEVER break a
tool call: every failure mode is swallowed.
"""
from __future__ import annotations

import json
import os
import threading
import time

_lock = threading.Lock()


def _usage_path() -> str:
    base = os.getenv("MEMORY_SERVER_DIR") or os.path.expanduser("~/.memory")
    data_dir = os.getenv("DATA_DIR") or os.path.join(base, "data")
    os.makedirs(os.path.join(data_dir, "metrics"), exist_ok=True)
    return os.path.join(data_dir, "metrics", "usage.jsonl")


def record_tool(name: str, latency_ms: float, ok: bool = True) -> None:
    """Record one tool call. Best-effort by design — never raises."""
    line = json.dumps({
        "ts": round(time.time(), 3),
        "tool": name,
        "ms": round(latency_ms, 1),
        "ok": bool(ok),
    })
    try:
        with _lock:
            with open(_usage_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass
