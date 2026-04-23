"""Unified MCP Memory Server — Single entry point for all memory services.

Consolidates automem, autodream, vk-cache, conversation-store, mem0, engram,
and sequential-thinking into ONE MCP server with prefixed tool names.

Uses public API only — no private _tool_manager access.
Each module's register_tools() function handles tool registration.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from shared.env_loader import load_env
load_env()
from shared.logging_config import setup_logging
setup_logging()
import logging
logger = logging.getLogger("agent-memory.unified")
from shared.config import Config
from shared.qdrant_client import QdrantClient
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MCP-agent-memory")
config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
_initialized = False

# ── Register all module tools via public API ────────────────────

_loaded = []
_failed = []

_MODULES = [
    ("automem",             "automem/"),
    ("autodream",           "autodream/"),
    ("vk_cache",            "vk-cache/"),
    ("conversation_store",  "conversation-store/"),
    ("mem0",                "mem0/"),
    ("engram",              "engram/"),
    ("sequential_thinking", "sequential-thinking/"),
]

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
        count = len(mcp._tool_manager._tools) - sum(t for _, t in _loaded)
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
STATUS_REPORT = (
    f"Unified Memory Server\n"
    f"  Modules: {len(_loaded)}/{len(_MODULES)} loaded\n"
    f"  Tools:   {_total} registered\n"
    + "\n".join(_status_lines)
)


async def _ensure_initialized() -> None:
    """Lazy initialization — runs once inside the MCP event loop."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    logger = logging.getLogger("mcp-agent-memory.init")

    # 1. Create all data directories
    dirs = [
        config.data_dir,
        config.engram_path,
        config.dream_path,
        config.thoughts_path,
        config.heartbeats_path,
        config.reminders_path,
        config.staging_buffer_path,
        config.vault_path,
    ]
    for d in dirs:
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)

    # 2. Ensure all Qdrant collections exist
    collections = {
        "automem": (config.qdrant_url, config.embedding_dim),
        "conversations": (config.qdrant_url, config.embedding_dim),
        "mem0_memories": (config.qdrant_url, config.embedding_dim),
    }
    for coll_name, (url, dim) in collections.items():
        try:
            client = QdrantClient(url, coll_name, dim)
            await client.ensure_collection(sparse=True)
            logger.info(f"Collection '{coll_name}' ready")
        except Exception as e:
            logger.warning(f"Collection '{coll_name}' init failed: {e}")

    # 3. Create engram subdirs
    for sub in ["general", "project", "personal", "model-packs"]:
        p = Path(config.engram_path) / sub if config.engram_path else None
        if p:
            p.mkdir(parents=True, exist_ok=True)

    # 4. Create vault folders
    for folder in ["Inbox", "Decisiones", "Conocimiento", "Episodios", "Entidades", "Notes"]:
        p = Path(config.vault_path) / folder if config.vault_path else None
        if p:
            p.mkdir(parents=True, exist_ok=True)

    logger.info("Initialization complete")


@mcp.tool()
async def health_check() -> dict:
    """Check health of all memory subsystems."""
    await _ensure_initialized()
    import asyncio
    checks = {}

    # Qdrant
    try:
        checks["qdrant"] = await qdrant.health()
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    # Embedding
    try:
        from shared.embedding import get_embedding
        vec = get_embedding("health check")
        checks["embedding"] = len(vec) == config.embedding_dim
    except Exception as e:
        checks["embedding"] = f"error: {e}"

    # Collection counts
    for coll in ["automem", "conversations", "mem0_memories"]:
        try:
            c = QdrantClient(config.qdrant_url, coll, config.embedding_dim)
            checks[f"{coll}_count"] = await c.count()
        except Exception:
            checks[f"{coll}_count"] = -1

    # Disk usage
    import os
    data_path = config.data_dir
    if data_path and os.path.exists(data_path):
        total = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fns in os.walk(data_path)
            for f in fns
        )
        checks["disk_mb"] = round(total / 1024 / 1024, 1)

    checks["modules_loaded"] = len(_loaded)
    checks["modules_failed"] = len(_failed)
    checks["tools_total"] = len(mcp._tool_manager._tools)
    checks["status"] = "ok" if not _failed else "degraded"
    return checks


def main() -> None:
    import logging
    from shared.logging_config import setup_logging
    setup_logging()
    logger = logging.getLogger("agent-memory")
    logger.info("Starting MCP server on stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
