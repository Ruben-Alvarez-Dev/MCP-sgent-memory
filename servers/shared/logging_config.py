"""Centralized logging configuration for all MCP memory server modules."""
from __future__ import annotations
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for all agent-memory modules.

    - Console output (stderr for MCP stdio compatibility)
    - Rotating file: ~/.memory/server.log (10MB, 3 backups)
    """
    log_dir = os.path.expanduser("~/.memory")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "server.log")

    root = logging.getLogger("agent-memory")
    if root.handlers:
        return  # Already configured

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # File handler with rotation
    fh = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    ))
    root.addHandler(fh)

    # Console handler (stderr — MCP uses stdout for protocol)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root.addHandler(ch)

    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
