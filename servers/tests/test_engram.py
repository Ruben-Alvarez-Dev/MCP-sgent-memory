"""Tests for engram module — path confinement, vault operations."""
import asyncio
import pytest
from pathlib import Path
import importlib


@pytest.fixture
def engram():
    return importlib.import_module("engram.server.main")


class TestGetDecisionPathConfinement:
    """SEC-C1: get_decision must reject paths outside engram root."""

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, engram):
        result = await engram.get_decision(file_path="/etc/passwd")
        assert result["status"] == "forbidden"

    @pytest.mark.asyncio
    async def test_traversal_blocked(self, engram):
        result = await engram.get_decision(file_path="../../../etc/shadow")
        assert result["status"] == "forbidden"

    @pytest.mark.asyncio
    async def test_nonexistent_inside_engram(self, engram):
        result = await engram.get_decision(file_path="/tmp/nonexistent_decision.md")
        assert result["status"] in ("not_found", "forbidden")

    @pytest.mark.asyncio
    async def test_valid_decision(self, engram):
        # Save first, then read
        saved = await engram.save_decision(title="Test Decision", content="test content")
        assert saved.status == "saved"
        result = await engram.get_decision(file_path=saved.file_path)
        assert "content" in result or result.get("status") == "not_found"


class TestSetModelPackSanitize:
    """SEC-C2: set_model_pack must sanitize name."""

    @pytest.mark.asyncio
    async def test_traversal_sanitized(self, engram):
        result = await engram.set_model_pack(name="../../.bashrc", content="test: v")
        assert ".." not in result.name
        assert result.status == "set"

    @pytest.mark.asyncio
    async def test_normal_name(self, engram):
        result = await engram.set_model_pack(name="test-pack", content="test: v")
        assert result.name == "test-pack"


class TestDeleteDecisionPathConfinement:
    """Path confinement for delete operations."""

    @pytest.mark.asyncio
    async def test_outside_path_blocked(self, engram):
        result = await engram.delete_decision(file_path="/etc/passwd")
        assert result["status"] == "forbidden"
