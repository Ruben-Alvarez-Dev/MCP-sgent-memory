"""Tests for shared.config — centralized configuration."""

import os
import pytest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import Config


class TestConfigDefaults:
    def test_default_values(self):
        c = Config()
        assert c.qdrant_url == "http://127.0.0.1:6333"
        assert c.embedding_dim == 1024
        assert c.embedding_backend == "llama_server"
        assert c.llm_backend == "ollama"

    def test_validate_ok(self):
        c = Config()
        assert c.validate() == []

    def test_validate_bad_dim(self):
        c = Config(embedding_dim=-1)
        errors = c.validate()
        assert any("EMBEDDING_DIM" in e for e in errors)

    def test_validate_bad_score(self):
        c = Config(vk_min_score=1.5)
        errors = c.validate()
        assert any("VK_MIN_SCORE" in e for e in errors)


class TestConfigFromEnv:
    def test_from_env_reads_vars(self, monkeypatch):
        monkeypatch.setenv("QDRANT_URL", "http://test:6333")
        monkeypatch.setenv("EMBEDDING_DIM", "512")
        monkeypatch.setenv("LLM_BACKEND", "lmstudio")
        c = Config.from_env()
        assert c.qdrant_url == "http://test:6333"
        assert c.embedding_dim == 512
        assert c.llm_backend == "lmstudio"
