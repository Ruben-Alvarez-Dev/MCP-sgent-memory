"""Centralized environment loader for all MCP memory server components.

Auto-discovers config/.env from:
  1. MEMORY_SERVER_DIR env var (if set externally)
  2. Relative to this file: ../../config/.env
  3. ~/.mcp-memory-server.env (user-level fallback)

Usage at the top of any server script:

    from env_loader import load_env
    load_env()

    # Now all os.getenv() calls return configured values.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_env_file() -> Path | None:
    """Find the central .env file."""
    # 1. Explicit override
    if os.getenv("MEMORY_SERVER_DIR"):
        candidate = Path(os.getenv("MEMORY_SERVER_DIR")) / "config" / ".env"
        if candidate.exists():
            return candidate

    # 2. Relative to this file (env_loader.py is in shared/)
    #    shared/env_loader.py → MCP-servers/config/.env
    for parent in [Path(__file__).resolve().parent]:
        for _ in range(4):
            parent = parent.parent
            candidate = parent / "config" / ".env"
            if candidate.exists():
                return candidate

    # 3. User-level fallback
    candidate = Path.home() / ".mcp-memory-server.env"
    if candidate.exists():
        return candidate

    return None


def load_env() -> Path:
    """Load the central .env file. Returns the path that was loaded.

    Sets environment variables for the current process.
    Does NOT overwrite variables already set (allows manual overrides).
    """
    env_file = _find_env_file()

    if env_file is None:
        # Silently skip — scripts use os.getenv() with defaults
        return Path("")

    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Expand ~ to home directory
            if "~" in value:
                value = os.path.expanduser(value)

            # Don't overwrite existing env vars (allows explicit overrides)
            if key not in os.environ:
                os.environ[key] = value

    return env_file


# Auto-load on import (convenient for scripts that just need the env)
_loaded_from = load_env()
