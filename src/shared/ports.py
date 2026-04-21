"""Dynamic port resolution for MCP Memory Server services.

Reads resolved ports from data/resolved_ports.json (created by configure.sh).
Falls back to env vars, then to sensible defaults.

Usage:
    from shared.ports import get_port
    qdrant_port = get_port("qdrant", 6333)
    llama_url = get_port_url("llama_server", 8081)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


_DEFAULTS = {
    "qdrant": 6333,
    "llama_server": 8081,
    "gateway": 3050,
    "ollama": 11434,
}

_PORTS_FILE: Optional[Path] = None


def _get_ports_file() -> Path:
    global _PORTS_FILE
    if _PORTS_FILE is not None:
        return _PORTS_FILE
    base = os.getenv("MEMORY_SERVER_DIR", ".")
    _PORTS_FILE = Path(base) / "data" / "resolved_ports.json"
    return _PORTS_FILE


def load_resolved_ports() -> dict[str, int]:
    """Load resolved ports from JSON file. Returns empty dict if not found."""
    try:
        f = _get_ports_file()
        if f.exists():
            return json.loads(f.read_text())
    except Exception:
        pass
    return {}


def get_port(service: str, default: Optional[int] = None) -> int:
    """Get port for a service. Priority: resolved_ports.json > env var > default."""
    # 1. Check resolved_ports.json
    resolved = load_resolved_ports()
    if service in resolved:
        return int(resolved[service])

    # 2. Check env var (e.g., QDRANT_PORT, LLAMA_SERVER_PORT)
    env_key = f"{service.upper().replace('-', '_')}_PORT"
    env_val = os.getenv(env_key)
    if env_val:
        return int(env_val)

    # 3. Fallback to default
    return default if default is not None else _DEFAULTS.get(service, 0)


def get_port_url(service: str, default_port: Optional[int] = None, host: str = "127.0.0.1") -> str:
    """Get full URL for a service (http://host:port)."""
    port = get_port(service, default_port)
    return f"http://{host}:{port}"


def save_resolved_ports(ports: dict[str, int]) -> None:
    """Save resolved ports to JSON file. Called by configure.sh."""
    f = _get_ports_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(ports, indent=2) + "\n")
