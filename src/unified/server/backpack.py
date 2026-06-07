"""Backpack API — Standalone HTTP server for plugin-to-server communication.

Runs INDEPENDENTLY from the MCP stdio server. Survives MCP client disconnects.

Architecture:
    Plugin hooks → fetch() → http://127.0.0.1:8890/api/* → Python functions → Qdrant

Usage:
    python -m unified.server.backpack
    # or
    python src/unified/server/backpack.py

Deploy with launchd, systemd, or nohup — this is a long-running daemon.
"""

from __future__ import annotations

import signal
import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from shared.env_loader import load_env
load_env()
from shared.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("agent-memory.backpack")

from shared.config import Config
from shared.qdrant_client import QdrantClient

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)

# ── Load module tool functions (same as unified/server/main.py) ─────

_MODULES = [
    ("L0_capture",              "L0_capture/"),
    ("L0_to_L4_consolidation",  "L0_to_L4_consolidation/"),
    ("L5_routing",              "L5_routing/"),
    ("L2_conversations",        "L2_conversations/"),
]

_loaded = {}
_failed = []

import importlib.util

for import_name, dir_name in _MODULES:
    try:
        mod_path = BASE_DIR / dir_name / "server" / "main.py"
        if not mod_path.exists():
            _failed.append((import_name, f"not found: {mod_path}"))
            continue
        spec = importlib.util.spec_from_file_location(import_name, str(mod_path))
        if not spec or not spec.loader:
            _failed.append((import_name, "bad spec"))
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[import_name] = mod
        spec.loader.exec_module(mod)
        _loaded[import_name] = mod
    except Exception as e:
        _failed.append((import_name, str(e)))

for name in _loaded:
    logger.info(f"  Loaded module: {name}")
for name, err in _failed:
    logger.warning(f"  Failed module: {name}: {err}")

# ── Resolve function references ─────────────────────────────────────

L0_capture_mod = _loaded.get("L0_capture")
L0_to_L4_consolidation_mod = _loaded.get("L0_to_L4_consolidation")
L2_conversations_mod = _loaded.get("L2_conversations")
L5_routing_mod = _loaded.get("L5_routing")

if not (L0_capture_mod and L0_to_L4_consolidation_mod and L2_conversations_mod):
    logger.error("Cannot start — missing required modules: L0_capture, L0_to_L4_consolidation, L2_conversations")
    sys.exit(1)

from shared.api_server import start_api_server

# ── Single-instance guard ───────────────────────────────────────────
# A second backpack must exit cleanly instead of crash-looping on the
# busy port (repair plan 2026-06-07, finding D2: OSError Errno 48).
_port = int(__import__("os").environ.get("AUTOMEM_API_PORT", "8890"))
import socket as _socket

_probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
try:
    _probe.bind(("127.0.0.1", _port))
except OSError:
    logger.info("Backpack already running on port %s — this instance exits "
                "cleanly (single-instance guard)", _port)
    raise SystemExit(0)
finally:
    _probe.close()

server = start_api_server(
    ingest_event_fn=getattr(L0_capture_mod, "ingest_event", None),
    L0_capture_heartbeat_fn=getattr(L0_capture_mod, "heartbeat", None),
    L0_to_L4_consolidation_heartbeat_fn=getattr(L0_to_L4_consolidation_mod, "heartbeat", None),
    save_conversation_fn=getattr(L2_conversations_mod, "save_conversation", None),
    consolidate_fn=getattr(L0_to_L4_consolidation_mod, "consolidate", None),
    request_context_fn=getattr(L5_routing_mod, "request_context", None) if L5_routing_mod else None,
    port=int(__import__("os").environ.get("AUTOMEM_API_PORT", "8890")),
)

logger.info("Backpack API daemon ready — press Ctrl+C to stop")

# ── Keep alive until signal ─────────────────────────────────────────

import threading

stop_event = threading.Event()


def _signal_handler(sig, frame):
    logger.info("Received signal %s — shutting down", sig)
    stop_event.set()


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ── Inbox scanner (repair plan P1) ──────────────────────────────────
# Every 60s: ingest each file dropped into <repo>/inbox/ (e.g. by
# scripts/cowork_bridge.sh) as a cowork_memory event, then archive it
# to inbox/processed/ so nothing is ingested twice.

INBOX_DIR = BASE_DIR.parent / "inbox"
INBOX_PROCESSED_DIR = INBOX_DIR / "processed"
INBOX_SCAN_INTERVAL_S = 60


def _inbox_scanner() -> None:
    import asyncio
    import shutil

    ingest = getattr(L0_capture_mod, "ingest_event", None)
    if ingest is None:
        logger.warning("Inbox scanner disabled — L0_capture.ingest_event missing")
        return
    # One persistent event loop for this thread's entire lifetime — same
    # pattern as shared/api_server.py _run_async. asyncio.run() per file
    # would create-and-close a loop on every call, leaving the shared
    # QdrantClient's pooled httpx connections bound to a dead loop and
    # failing later stores with "Event loop is closed".
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while not stop_event.wait(INBOX_SCAN_INTERVAL_S):
            try:
                if not INBOX_DIR.is_dir():
                    continue
                INBOX_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
                for f in sorted(INBOX_DIR.iterdir()):
                    if not f.is_file() or f.name.startswith("."):
                        continue
                    content = f.read_text(errors="replace")
                    loop.run_until_complete(ingest(
                        event_type="cowork_memory", source=f"inbox:{f.name}",
                        content=content, actor_id="ruben",
                    ))
                    shutil.move(str(f), str(INBOX_PROCESSED_DIR / f.name))
                    logger.info("Inbox scanner: ingested %s", f.name)
            except Exception as e:
                logger.warning("Inbox scanner error: %s", e)
    finally:
        loop.close()


threading.Thread(target=_inbox_scanner, daemon=True, name="inbox-scanner").start()
logger.info("Inbox scanner watching %s every %ss", INBOX_DIR, INBOX_SCAN_INTERVAL_S)

stop_event.wait()
server.shutdown()
logger.info("Backpack API stopped")
