"""Unified MCP Memory Server — Single entry point for all memory services.

Consolidates automem, autodream, vk-cache, conversation-store, mem0, engram,
and sequential-thinking into ONE MCP server with prefixed tool names.

Tool naming: {module}_{original_name}
  e.g. automem_memorize, autodream_consolidate, engram_save_decision, etc.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────
# BASE_DIR resolves to the root of the code (MCP-servers/ in repo, src/ in install)
# PYTHONPATH must be set to BASE_DIR for shared.* imports to work.
BASE_DIR = Path(__file__).resolve().parents[2]

# ── Load env BEFORE importing any server modules ──────────────────
sys.path.insert(0, str(BASE_DIR))

from shared.env_loader import load_env
load_env()

from mcp.server.fastmcp import FastMCP

# ── Unified server ─────────────────────────────────────────────────
mcp = FastMCP("memory")

# ── Module registry ────────────────────────────────────────────────
# Each entry: (import_name, filesystem_path, tool_prefix)
SERVER_MODULES = [
    ("automem",             BASE_DIR / "automem"             / "server" / "main.py", "automem"),
    ("autodream",           BASE_DIR / "autodream"           / "server" / "main.py", "autodream"),
    ("vk_cache",            BASE_DIR / "vk-cache"            / "server" / "main.py", "vk_cache"),
    ("conversation_store",  BASE_DIR / "conversation-store"  / "server" / "main.py", "conversation_store"),
    ("mem0",                BASE_DIR / "mem0"                / "server" / "main.py", "mem0"),
    ("engram",              BASE_DIR / "engram"              / "server" / "main.py", "engram"),
    ("sequential_thinking", BASE_DIR / "sequential-thinking" / "server" / "main.py", "sequential_thinking"),
]

loaded = []
failed = []

for mod_name, mod_path, prefix in SERVER_MODULES:
    try:
        if not mod_path.exists():
            failed.append((mod_name, f"File not found: {mod_path}"))
            continue

        spec = importlib.util.spec_from_file_location(mod_name, str(mod_path))
        if spec is None or spec.loader is None:
            failed.append((mod_name, "Could not create module spec"))
            continue

        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

        module_mcp = getattr(mod, "mcp", None)
        if module_mcp is None:
            failed.append((mod_name, "No 'mcp' instance found in module"))
            continue

        tool_count = 0
        for tool_name, tool in module_mcp._tool_manager._tools.items():
            prefixed_name = f"{prefix}_{tool_name}"
            mcp.add_tool(tool.fn, name=prefixed_name)
            tool_count += 1

        loaded.append((mod_name, prefix, tool_count))

    except Exception as e:
        failed.append((mod_name, str(e)))

# ── Status report ──────────────────────────────────────────────────
_total_tools = sum(t[2] for t in loaded)
_lines = [f"  ✓ {name} ({prefix}): {count} tools" for name, prefix, count in loaded]
_lines += [f"  ✗ {name}: {err}" for name, err in failed]
STATUS_REPORT = (
    f"Unified Memory Server\n"
    f"  Modules: {len(loaded)}/{len(SERVER_MODULES)} loaded\n"
    f"  Tools:   {_total_tools} registered\n"
    + "\n".join(_lines)
)


def main() -> None:
    """Entry point — runs the unified server on stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
