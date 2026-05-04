"""Unified MCP Memory Server — Single entry point for all memory services.

Consolidates L0-capture, L0-to-L4-consolidation, L5-routing, L2-conversations, L3-facts, L3-decisions,
and Lx-reasoning into ONE MCP server with prefixed tool names.

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

mcp = FastMCP("agent-memory")
config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, config.qdrant_collection, config.embedding_dim)
_initialized = False

# ── Register all module tools via public API ────────────────────

_loaded = []
_failed = []

_MODULES = [
    ("L0_capture",                  "L0_capture/"),
    ("L0_to_L4_consolidation",      "L0_to_L4_consolidation/"),
    ("L5_routing",                  "L5_routing/"),
    ("L2_conversations",            "L2_conversations/"),
    ("L3_facts",                    "L3_facts/"),
    ("L3_decisions",                "L3_decisions/"),
    ("Lx_reasoning",                "Lx_reasoning/"),
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
        config.L3_decisions_path,
        config.L4_narrative_path,
        config.Lx_deliberative_path,
        config.L1_working_path,
        config.L5_selective_path,
        config.tmp_path,
        config.Lx_persistent_path,
    ]
    for d in dirs:
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)

    # 2. Ensure all Qdrant collections exist
    collections = {
        "L0_L4_memory": (config.qdrant_url, config.embedding_dim),
        "L2_conversations": (config.qdrant_url, config.embedding_dim),
        "L3_facts": (config.qdrant_url, config.embedding_dim),
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
        p = Path(config.L3_decisions_path) / sub if config.L3_decisions_path else None
        if p:
            p.mkdir(parents=True, exist_ok=True)

    # 4. Create vault folders
    for folder in ["inbox", "decisions", "knowledge", "episodes", "entities", "Notes"]:
        p = Path(config.Lx_persistent_path) / folder if config.Lx_persistent_path else None
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
    for coll in ["L0_L4_memory", "L2_conversations", "L3_facts"]:
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
    import os
    from shared.logging_config import setup_logging
    setup_logging()
    logger = logging.getLogger("agent-memory")

    # ── Start Backpack HTTP API sidecar ────────────────────────────
    # Runs in a background thread alongside the MCP stdio server.
    # Plugin hooks call these endpoints via fetch() to trigger automatic
    # memory operations without involving the LLM.
    try:
        from shared.api_server import start_api_server

        # Import the tool functions from loaded modules.
        # These modules were loaded above via importlib, so they exist in sys.modules.
        L0_capture_mod = sys.modules.get("L0_capture")
        L0_to_L4_consolidation_mod = sys.modules.get("L0_to_L4_consolidation")
        L2_conversations_mod = sys.modules.get("L2_conversations")
        L5_routing_mod = sys.modules.get("L5_routing")

        if L0_capture_mod and L0_to_L4_consolidation_mod and L2_conversations_mod:
            start_api_server(
                ingest_event_fn=getattr(L0_capture_mod, "ingest_event", None),
                automem_heartbeat_fn=getattr(L0_capture_mod, "heartbeat", None),
                autodream_heartbeat_fn=getattr(L0_to_L4_consolidation_mod, "heartbeat", None),
                save_conversation_fn=getattr(L2_conversations_mod, "save_conversation", None),
                consolidate_fn=getattr(L0_to_L4_consolidation_mod, "consolidate", None),
                request_context_fn=getattr(L5_routing_mod, "request_context", None) if L5_routing_mod else None,
                port=int(os.environ.get("AUTOMEM_API_PORT", "8890")),
            )
            logger.info("Backpack API sidecar started")
        else:
            logger.warning("Backpack API skipped: not all modules loaded")
    except Exception as e:
        logger.warning("Backpack API failed to start (non-fatal): %s", e)

    logger.info("Starting MCP server on stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
