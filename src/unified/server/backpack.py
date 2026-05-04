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

stop_event.wait()
server.shutdown()
logger.info("Backpack API stopped")
