"""Tests for MCP tool modules — L0 capture, L3 facts/decisions, L4 consolidation, L5 routing.

These tests use mocking for Qdrant/embedding — no external services needed.
They verify that the MCP tool functions return correct Result types.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


# ── L0 Capture ─────────────────────────────────────────────────────


class TestL0Capture:
    def test_register_tools_creates_mcp_tools(self):
        from L0_capture.server.main import register_tools
        from mcp.server.fastmcp import FastMCP
        fake_mcp = MagicMock(spec=FastMCP)
        fake_qdrant = MagicMock()
        fake_config = MagicMock()
        fake_config.embedding_dim = 1024
        fake_config.qdrant_url = "http://localhost:6333"
        fake_mcp.add_tool = MagicMock()
        register_tools(fake_mcp, fake_qdrant, fake_config)
        assert fake_mcp.add_tool.call_count >= 4

    def test_memorize_result(self):
        from shared.result_models import MemorizeResult
        r = MemorizeResult(memory_id="123", layer="L0", scope="session")
        assert r.memory_id == "123"
        assert r.layer == "L0"
        assert r.status == "stored"

    def test_ingest_result(self):
        from shared.result_models import IngestResult
        r = IngestResult(event_id="e-1", layer="L0")
        assert r.event_id == "e-1"
        assert r.status == "ingested"

    def test_heartbeat_result(self):
        from shared.result_models import HeartbeatResult
        r = HeartbeatResult(agent_id="test", turn_count=1)
        assert r.agent_id == "test"
        assert r.turn_count == 1
        assert r.status == "active"

    def test_status_result(self):
        from shared.result_models import L0CaptureStatusResult
        r = L0CaptureStatusResult()
        assert r.daemon == "L0_capture"
        assert r.status == "RUNNING"


# ── L3 Facts ───────────────────────────────────────────────────────


class TestL3Facts:
    def test_add_memory_result(self):
        from shared.result_models import AddMemoryResult
        r = AddMemoryResult(memory_id="abc")
        assert r.memory_id == "abc"
        assert r.status == "added"

    def test_search_result(self):
        from shared.result_models import SearchResult
        r = SearchResult(count=1, results=[{"content": "test"}])
        assert r.count == 1

    def test_l3_facts_status(self):
        from shared.result_models import L3FactsStatusResult
        r = L3FactsStatusResult()
        assert r.daemon == "L3_facts"


# ── L3 Decisions ───────────────────────────────────────────────────


class TestL3Decisions:
    def test_save_decision_result(self):
        from shared.result_models import SaveDecisionResult
        r = SaveDecisionResult(file_path="decisions/test.md", title="test")
        assert r.file_path.endswith(".md")
        assert r.title == "test"

    def test_list_decisions_result(self):
        from shared.result_models import DecisionListResult
        r = DecisionListResult(count=2, decisions=[{"file": "a.md"}, {"file": "b.md"}])
        assert r.count == 2

    def test_l3_decisions_status(self):
        from shared.result_models import L3DecisionsStatusResult
        r = L3DecisionsStatusResult()
        assert r.daemon == "L3_decisions"


# ── L4 Consolidation ───────────────────────────────────────────────


class TestL4Consolidation:
    def test_consolidate_result(self):
        from shared.result_models import ConsolidateResult
        r = ConsolidateResult(results=["L0→L1"])
        assert r.status == "consolidation complete"
        assert "L0→L1" in r.results

    def test_dream_result(self):
        from shared.result_models import DreamResult
        r = DreamResult(status="dreaming", total_dreams=3)
        assert r.total_dreams == 3

    def test_auto_dream_status(self):
        from shared.result_models import AutoDreamStatusResult
        r = AutoDreamStatusResult()
        assert r.daemon == "AutoDream"


# ── L5 Routing ─────────────────────────────────────────────────────


class TestL5Routing:
    def test_context_pack_result(self):
        from shared.result_models import ContextPackResult
        r = ContextPackResult(injection_text="Based on context...")
        assert r.injection_text.startswith("Based on")

    def test_reminder_push_result(self):
        from shared.result_models import ReminderPushResult
        r = ReminderPushResult(reminder_id="r-1", sources=0)
        assert r.status == "reminder_pushed"

    def test_reminder_list_result(self):
        from shared.result_models import ReminderListResult
        r = ReminderListResult(agent_id="test", reminders=[], count=0)
        assert r.reminders == []

    def test_context_shift_result(self):
        from shared.result_models import ContextShiftResult
        r = ContextShiftResult(shift_detected=False, similarity=0.9)
        assert r.shift_detected is False

    def test_vk_cache_status(self):
        from shared.result_models import VkCacheStatusResult
        r = VkCacheStatusResult()
        assert r.daemon == "L5_routing"

    def test_request_context_signature(self):
        import inspect
        import L5_routing.server.main as l5
        sig = inspect.signature(l5.request_context)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "token_budget" in params
        assert "intent" in params


# ── Result Model Consistency ────────────────────────────────────────


class TestResultModelConsistency:
    def test_all_status_models_have_daemon(self):
        """All *StatusResult models should have a 'daemon' field."""
        from shared.result_models import (
            L0CaptureStatusResult, L3FactsStatusResult, L3DecisionsStatusResult,
            AutoDreamStatusResult, VkCacheStatusResult, ConversationStatusResult,
        )
        for cls in [L0CaptureStatusResult, L3FactsStatusResult, L3DecisionsStatusResult,
                    AutoDreamStatusResult, VkCacheStatusResult, ConversationStatusResult]:
            instance = cls()
            assert hasattr(instance, 'daemon'), f"{cls.__name__} missing 'daemon'"
            assert isinstance(instance.daemon, str) and len(instance.daemon) > 0

    def test_all_status_models_default_to_running(self):
        """All *StatusResult models default to 'RUNNING'."""
        from shared.result_models import (
            L0CaptureStatusResult, L3FactsStatusResult, L3DecisionsStatusResult,
            AutoDreamStatusResult, VkCacheStatusResult, ConversationStatusResult,
        )
        for cls in [L0CaptureStatusResult, L3FactsStatusResult, L3DecisionsStatusResult,
                    AutoDreamStatusResult, VkCacheStatusResult, ConversationStatusResult]:
            instance = cls()
            assert instance.status == "RUNNING", f"{cls.__name__} status is '{instance.status}', expected 'RUNNING'"

    def test_all_result_models_exported(self):
        """All result models should be importable from shared.result_models."""
        from shared import result_models as rm
        expected = [
            "MemorizeResult", "IngestResult", "HeartbeatResult",
            "L0CaptureStatusResult", "AddMemoryResult", "SearchResult",
            "SaveDecisionResult", "DecisionListResult", "L3FactsStatusResult",
            "L3DecisionsStatusResult", "ConsolidateResult", "DreamResult",
            "AutoDreamStatusResult", "ContextPackResult", "ReminderPushResult",
            "ReminderListResult", "ContextShiftResult", "VkCacheStatusResult",
            "ConversationStatusResult", "SaveConversationResult",
            "VaultWriteResult", "VaultIntegrityResult",
        ]
        for name in expected:
            assert hasattr(rm, name), f"Missing: {name}"
