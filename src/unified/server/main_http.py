"""Unified Memory Server — HTTP transport (Fase 3C: streamable-http).

Same as main.py but runs on streamable-http instead of stdio.
Allows multiple MCP clients to connect simultaneously.

Usage:
    python -m unified.server.main_http --port 8080

Or:
    MEMORY_TRANSPORT=streamable-http MEMORY_PORT=8080 python -m unified.server.main
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Reuse ALL the module loading from main.py
# Only change: the transport at the end
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from mcp.server.fastmcp import FastMCP

config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
mcp = FastMCP("unified-memory-server")

# ── Load all modules (same as main.py) ──────────────────────────

_MODULES = [
    ("automem",             "automem/"),
    ("autodream",           "autodream/"),
    ("vk_cache",            "vk-cache/"),
    ("conversation_store",  "conversation-store/"),
    ("mem0",                "mem0/"),
    ("engram",              "engram/"),
    ("sequential_thinking", "sequential-thinking/"),
]

_loaded = []
_failed = []

for import_name, dir_name, prefix in [(n, d, f"{n}_") for n, d in _MODULES]:
    try:
        import importlib.util
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
        if not hasattr(mod, "register_tools"):
            _failed.append((import_name, "no register_tools()"))
            continue
        mod.register_tools(mcp, qdrant, config, prefix=prefix)
        _loaded.append((import_name, len(mcp._tool_manager._tools)))
    except Exception as e:
        _failed.append((import_name, str(e)))

_total = len(mcp._tool_manager._tools)
_status_lines = []
_prev = 0
for name, total in _loaded:
    _status_lines.append(f"  ✓ {name}: {total - _prev} tools")
    _prev = total
_status_lines += [f"  ✗ {n}: {e}" for n, e in _failed]

logger.info(
    "Unified Memory Server (HTTP)\n"
    "  Total tools: %d\n"
    "%s",
    _total,
    "\n".join(_status_lines),
)


def main():
    port = int(os.environ.get("MEMORY_PORT", "8080"))
    logger.info("Starting MCP server on streamable-http :%d", port)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
