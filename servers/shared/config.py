"""Centralized configuration for all MCP memory servers.

Single source of truth for all configuration values.
Replaces scattered os.getenv() calls across 7 server modules.

Usage:
    from shared.config import Config

    config = Config.from_env()
    print(config.qdrant_url)       # http://127.0.0.1:6333
    print(config.embedding_dim)    # 1024

    errors = config.validate()
    if errors:
        raise RuntimeError(f"Config errors: {errors}")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Type-safe configuration loaded from environment variables."""

    # ── Qdrant ────────────────────────────────────────────────
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "automem"

    # ── Embedding ─────────────────────────────────────────────
    embedding_backend: str = "llama_server"
    embedding_dim: int = 1024
    embedding_model: str = ""
    llama_server_url: str = "http://127.0.0.1:8081"
    embedding_cache_size: int = 512

    # ── LLM ───────────────────────────────────────────────────
    llm_backend: str = "ollama"
    llm_model: str = "qwen2.5:7b"

    # ── Paths ─────────────────────────────────────────────────
    server_dir: str = ""
    data_dir: str = ""
    vault_path: str = ""
    engram_path: str = ""
    dream_path: str = ""
    thoughts_path: str = ""
    heartbeats_path: str = ""
    reminders_path: str = ""
    staging_buffer_path: str = ""
    raw_events_jsonl: str = ""

    # ── Scheduling ────────────────────────────────────────────
    automem_promote_every: int = 10
    dream_promote_l1: int = 10
    dream_promote_l2: int = 3600
    dream_promote_l3: int = 86400
    dream_promote_l4: int = 604800

    # ── vk-cache ──────────────────────────────────────────────
    vk_min_score: float = 0.3
    vk_max_items: int = 8
    vk_max_tokens: int = 8000

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables.

        Call shared.env_loader.load_env() first to populate env vars
        from .env file.
        """
        server_dir = os.getenv("MEMORY_SERVER_DIR", "")

        return cls(
            # Qdrant
            qdrant_url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "automem"),
            # Embedding
            embedding_backend=os.getenv("EMBEDDING_BACKEND", "llama_server"),
            embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
            embedding_model=os.getenv("EMBEDDING_MODEL", ""),
            llama_server_url=os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8081"),
            embedding_cache_size=int(os.getenv("EMBEDDING_CACHE_SIZE", "512")),
            # LLM
            llm_backend=os.getenv("LLM_BACKEND", "ollama"),
            llm_model=os.getenv("LLM_MODEL", "qwen2.5:7b"),
            # Paths
            server_dir=server_dir,
            data_dir=os.getenv("DATA_DIR", os.path.join(server_dir, "data") if server_dir else ""),
            vault_path=os.getenv("VAULT_PATH", os.path.join(server_dir, "vault") if server_dir else ""),
            engram_path=os.getenv("ENGRAM_PATH", os.path.join(server_dir, "data", "memory", "engram") if server_dir else ""),
            dream_path=os.getenv("DREAM_PATH", os.path.join(server_dir, "data", "memory", "dream") if server_dir else ""),
            thoughts_path=os.getenv("THOUGHTS_PATH", os.path.join(server_dir, "data", "memory", "thoughts") if server_dir else ""),
            heartbeats_path=os.getenv("HEARTBEATS_PATH", os.path.join(server_dir, "data", "memory", "heartbeats") if server_dir else ""),
            reminders_path=os.getenv("REMINDERS_PATH", os.path.join(server_dir, "data", "memory", "reminders") if server_dir else ""),
            staging_buffer_path=os.getenv("STAGING_BUFFER", os.path.join(server_dir, "data", "staging_buffer") if server_dir else ""),
            raw_events_jsonl=os.getenv("AUTOMEM_JSONL", os.path.join(server_dir, "data", "raw_events.jsonl") if server_dir else ""),
            # Scheduling
            automem_promote_every=int(os.getenv("AUTOMEM_PROMOTE_EVERY", "10")),
            dream_promote_l1=int(os.getenv("DREAM_PROMOTE_L1", "10")),
            dream_promote_l2=int(os.getenv("DREAM_PROMOTE_L2", "3600")),
            dream_promote_l3=int(os.getenv("DREAM_PROMOTE_L3", "86400")),
            dream_promote_l4=int(os.getenv("DREAM_PROMOTE_L4", "604800")),
            # vk-cache
            vk_min_score=float(os.getenv("VK_MIN_SCORE", "0.3")),
            vk_max_items=int(os.getenv("VK_MAX_ITEMS", "8")),
            vk_max_tokens=int(os.getenv("VK_MAX_TOKENS", "8000")),
        )

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of error messages."""
        errors: list[str] = []

        if not self.qdrant_url:
            errors.append("QDRANT_URL is empty")
        if self.embedding_dim <= 0:
            errors.append(f"EMBEDDING_DIM must be > 0, got {self.embedding_dim}")
        if self.embedding_cache_size < 0:
            errors.append(f"EMBEDDING_CACHE_SIZE must be >= 0, got {self.embedding_cache_size}")
        if self.vk_min_score < 0 or self.vk_min_score > 1:
            errors.append(f"VK_MIN_SCORE must be 0-1, got {self.vk_min_score}")

        return errors
