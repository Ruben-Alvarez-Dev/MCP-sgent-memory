"""Centralized environment + path loader for all MCP memory server components.

Single source of truth for ALL paths. Everything lives inside MEMORY_SERVER_DIR.
Nothing outside. Ever.

Auto-discovers config/.env by walking up from this file until it finds config/.env.
Then sets up all data paths relative to the discovered project root.

Layout (same in dev and prod):
    PROJECT_ROOT/
    ├── config/.env
    ├── data/
    │   ├── memory/          ← engram, dream, thoughts, heartbeats, reminders
    │   ├── qdrant/          ← vector DB storage
    │   ├── logs/            ← service logs
    │   ├── raw_events.jsonl ← L0 audit trail
    │   └── staging_buffer/  ← temp staging
    ├── engine/              ← llama.cpp binaries
    ├── models/              ← .gguf embedding models
    ├── bin/                 ← Qdrant binary
    ├── src/ (or directly)   ← server code + shared/
    └── vault/               ← Obsidian vault

Usage at the top of any server script:

    from env_loader import load_env
    load_env()

    # Now all os.getenv() calls return configured values.
    # All paths are relative to PROJECT_ROOT.
"""

from __future__ import annotations

import os
from pathlib import Path

# Will be set by load_env()
_project_root: Path | None = None


def find_project_root() -> Path:
    """Find the project root by walking up from this file.

    Looks for config/.env or src/shared/__init__.py or shared/__init__.py.
    """
    global _project_root
    if _project_root is not None:
        return _project_root

    # 1. Explicit override
    env_dir = os.getenv("MEMORY_SERVER_DIR", "")
    if env_dir and Path(env_dir).exists():
        _project_root = Path(env_dir)
        return _project_root

    # 2. Walk up from this file until we find config/.env
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "config" / ".env").exists():
            _project_root = parent
            return _project_root
        # Also check if this is the root by looking for shared/
        if (parent / "shared" / "__init__.py").exists() and (parent / "config").exists():
            _project_root = parent
            return _project_root

    # 3. Last resort: parent of shared/
    for parent in [current] + list(current.parents):
        if (parent / "shared" / "__init__.py").exists():
            _project_root = parent
            return _project_root

    # Give up — use current working directory
    _project_root = Path.cwd()
    return _project_root


def _find_env_file() -> Path | None:
    """Find the central .env file."""
    root = find_project_root()
    candidate = root / "config" / ".env"
    if candidate.exists():
        return candidate
    return None


def _setup_data_paths(root: Path) -> None:
    """Set all data paths relative to project root if not already set.

    These become the DEFAULT values — env vars in .env or launchd can override.
    But if nothing is set, everything goes to data/ inside the project root.
    """
    data = root / "data"
    mem = data / "memory"

    # Create dirs if they don't exist
    for d in [
        data, mem,
        mem / "engram", mem / "dream", mem / "thoughts",
        mem / "heartbeats", mem / "reminders",
        data / "qdrant", data / "logs", data / "staging_buffer",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Set env vars ONLY if not already set (allow overrides)
    defaults = {
        # Data paths
        "DATA_DIR": str(data),
        "MEMORY_DIR": str(mem),
        "AUTOMEM_JSONL": str(data / "raw_events.jsonl"),
        "STAGING_BUFFER": str(data / "staging_buffer"),
        "ENGRAM_PATH": str(mem / "engram"),
        "DREAM_PATH": str(mem / "dream"),
        "THOUGHTS_PATH": str(mem / "thoughts"),
        "HEARTBEATS_PATH": str(mem / "heartbeats"),
        "REMINDERS_PATH": str(mem / "reminders"),

        # Qdrant
        "QDRANT_DATA": str(data / "qdrant"),

        # Logs
        "LOG_DIR": str(data / "logs"),

        # Vault
        "VAULT_PATH": str(root / "data" / "vault"),

        # Observe
        "OBSERVE_LOG_DIR": str(data / "logs" / "observe"),
    }

    for key, value in defaults.items():
        if key not in os.environ:
            os.environ[key] = value

    # Always set MEMORY_SERVER_DIR if not set
    if "MEMORY_SERVER_DIR" not in os.environ:
        os.environ["MEMORY_SERVER_DIR"] = str(root)


def load_env() -> Path:
    """Load the central .env file. Returns the path that was loaded.

    1. Find project root
    2. Set up all data paths relative to root
    3. Load .env (overrides defaults but NOT existing env vars)
    """
    root = find_project_root()

    # Set up default data paths first
    _setup_data_paths(root)

    # Load .env on top (won't overwrite existing)
    env_file = _find_env_file()
    if env_file is None:
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

            # Remove quotes
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Expand $VAR references to already-set env vars
            import re
            def _expand(m):
                return os.getenv(m.group(1), m.group(0))
            value = re.sub(r'\$(\w+)', _expand, value)

            # Expand ~ to home
            if "~" in value:
                value = os.path.expanduser(value)

            # Don't overwrite existing (allows explicit overrides)
            if key not in os.environ:
                os.environ[key] = value

    return env_file if env_file else Path("")


def get_config() -> "Config":
    """Load env and return a Config instance. Convenience function."""
    from shared.config import Config
    load_env()
    return Config.from_env()
