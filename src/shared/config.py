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
    qdrant_collection: str = "L0_L4_memory"

    # ── Embedding ─────────────────────────────────────────────
    embedding_backend: str = "llama_server"
    embedding_dim: int = 1024
    embedding_model: str = ""
    llama_server_url: str = "http://127.0.0.1:8081"
    embedding_cache_size: int = 512

    # ── LLM ───────────────────────────────────────────────────
    llm_backend: str = "llama_cpp"
    llm_model: str = "qwen2.5:7b"

    # ── Paths ─────────────────────────────────────────────────
    server_dir: str = ""
    data_dir: str = ""
    Lx_persistent_path: str = ""
    L3_decisions_path: str = ""
    L4_narrative_path: str = ""
    Lx_deliberative_path: str = ""
    L1_working_path: str = ""
    L5_selective_path: str = ""
    tmp_path: str = ""
    L0_events_jsonl: str = ""

    # ── Scheduling ────────────────────────────────────────────
    L0_capture_promote_every: int = 10
    consolidation_promote_L1: int = 10
    consolidation_promote_L2: int = 3600
    consolidation_promote_L3: int = 86400
    consolidation_promote_L4: int = 604800

    # ── vk-cache ──────────────────────────────────────────────
    L5_routing_min_score: float = 0.3
    L5_routing_max_items: int = 8
    L5_routing_max_tokens: int = 8000

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
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "L0_L4_memory"),
            # Embedding
            embedding_backend=os.getenv("EMBEDDING_BACKEND", "llama_server"),
            embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
            embedding_model=os.getenv("EMBEDDING_MODEL", ""),
            llama_server_url=os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8081"),
            embedding_cache_size=int(os.getenv("EMBEDDING_CACHE_SIZE", "512")),
            # LLM
            llm_backend=os.getenv("LLM_BACKEND", "llama_cpp"),
            llm_model=os.getenv("LLM_MODEL", "qwen2.5:7b"),
            # Paths
            server_dir=server_dir,
            data_dir=os.getenv("DATA_DIR", os.path.join(server_dir, "data") if server_dir else ""),
            Lx_persistent_path=os.getenv("VAULT_PATH", os.path.join(server_dir, "data", "Lx-persistent") if server_dir else ""),
            L3_decisions_path=os.getenv("L3_DECISIONS_PATH", os.path.join(server_dir, "data", "L3-semantic", "decisions") if server_dir else ""),
            L4_narrative_path=os.getenv("L4_NARRATIVE_PATH", os.path.join(server_dir, "data", "L4-narrative") if server_dir else ""),
            Lx_deliberative_path=os.getenv("LX_DELIBERATIVE_PATH", os.path.join(server_dir, "data", "Lx-deliberative", "sessions") if server_dir else ""),
            L1_working_path=os.getenv("L1_WORKING_PATH", os.path.join(server_dir, "data", "L1-working", "agents") if server_dir else ""),
            L5_selective_path=os.getenv("L5_SELECTIVE_PATH", os.path.join(server_dir, "data", "L5-selective", "reminders") if server_dir else ""),
            tmp_path=os.getenv("TMP_PATH", os.path.join(server_dir, "tmp") if server_dir else ""),
            L0_events_jsonl=os.getenv("L0_EVENTS_PATH", os.path.join(server_dir, "data", "L0-sensory", "events.jsonl") if server_dir else ""),
            # Scheduling
            L0_capture_promote_every=int(os.getenv("L0_CAPTURE_PROMOTE_EVERY", "10")),
            consolidation_promote_L1=int(os.getenv("CONSOLIDATION_PROMOTE_L1", "10")),
            consolidation_promote_L2=int(os.getenv("CONSOLIDATION_PROMOTE_L2", "3600")),
            consolidation_promote_L3=int(os.getenv("CONSOLIDATION_PROMOTE_L3", "86400")),
            consolidation_promote_L4=int(os.getenv("CONSOLIDATION_PROMOTE_L4", "604800")),
            # vk-cache
            L5_routing_min_score=float(os.getenv("L5_ROUTING_MIN_SCORE", "0.3")),
            L5_routing_max_items=int(os.getenv("L5_ROUTING_MAX_ITEMS", "8")),
            L5_routing_max_tokens=int(os.getenv("L5_ROUTING_MAX_TOKENS", "8000")),
        )

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of error messages."""
        errors: list[str] = []

        # URLs
        if not self.qdrant_url:
            errors.append("QDRANT_URL is empty")
        elif not self.qdrant_url.startswith(("http://", "https://")):
            errors.append(f"QDRANT_URL must be http(s) URL, got {self.qdrant_url}")
        else:
            # Validate port is in valid range
            try:
                from urllib.parse import urlparse
                port = urlparse(self.qdrant_url).port
                if port is not None and not (1 <= port <= 65535):
                    errors.append(f"QDRANT_URL port out of range: {port}")
            except ValueError:
                errors.append(f"QDRANT_URL has invalid port number")
                pass

        # Embedding backend
        valid_embed_backends = {"llama_cpp", "llama_server", "http", "noop"}
        if self.embedding_backend not in valid_embed_backends:
            errors.append(f"EMBEDDING_BACKEND must be one of {valid_embed_backends}, got '{self.embedding_backend}'")

        # LLM backend
        valid_llm_backends = {"llama_cpp"}
        if self.llm_backend not in valid_llm_backends:
            errors.append(f"LLM_BACKEND must be one of {valid_llm_backends}, got '{self.llm_backend}'")

        # Embedding dimension
        standard_dims = {256, 384, 512, 768, 1024, 1536}
        if self.embedding_dim <= 0:
            errors.append(f"EMBEDDING_DIM must be > 0, got {self.embedding_dim}")
        elif self.embedding_dim not in standard_dims:
            errors.append(f"EMBEDDING_DIM unusual value: {self.embedding_dim} (standard: {sorted(standard_dims)})")

        # Cache
        if self.embedding_cache_size < 0:
            errors.append(f"EMBEDDING_CACHE_SIZE must be >= 0, got {self.embedding_cache_size}")

        # vk-cache
        if not (0 <= self.L5_routing_min_score <= 1):
            errors.append(f"L5_ROUTING_MIN_SCORE must be 0-1, got {self.L5_routing_min_score}")

        # Model path for llama_server backend
        if self.embedding_backend == "llama_server" and self.embedding_model:
            if not Path(self.embedding_model).exists():
                errors.append(f"EMBEDDING_MODEL not found: {self.embedding_model}")

        return errors
