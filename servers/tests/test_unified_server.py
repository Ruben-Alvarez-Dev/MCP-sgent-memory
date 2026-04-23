"""Integration test: unified server loads all modules with correct tool count."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib.util
import pytest


def test_unified_server_loads():
    """Verify unified server loads 7 modules with 50 tools, no private API."""
    from shared.env_loader import load_env
    load_env()

    spec = importlib.util.spec_from_file_location(
        "unified", os.path.join(os.path.dirname(__file__), "..", "unified", "server", "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._total == 50, f"Expected 50 tools, got {mod._total}"
    assert len(mod._loaded) == 7, f"Expected 7 modules, got {len(mod._loaded)}"
    assert len(mod._failed) == 0, f"Failed modules: {mod._failed}"

    # Verify no private API access in source
    source_path = os.path.join(os.path.dirname(__file__), "..", "unified", "server", "main.py")
    with open(source_path) as f:
        source = f.read()
    assert "_tool_manager" not in source, "Unified server uses private _tool_manager API"
    assert "_tools" not in source, "Unified server uses private _tools API"


def test_all_modules_have_register_tools():
    """Verify all 7 modules export register_tools()."""
    from shared.env_loader import load_env
    load_env()

    modules = [
        ("automem", "automem/server/main.py"),
        ("autodream", "autodream/server/main.py"),
        ("vk-cache", "vk-cache/server/main.py"),
        ("conversation-store", "conversation-store/server/main.py"),
        ("mem0", "mem0/server/main.py"),
        ("engram", "engram/server/main.py"),
        ("sequential-thinking", "sequential-thinking/server/main.py"),
    ]

    base = os.path.join(os.path.dirname(__file__), "..")
    for name, path in modules:
        spec = importlib.util.spec_from_file_location(name, os.path.join(base, path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "register_tools"), f"{name} missing register_tools()"
        assert len(mod.mcp._tool_manager._tools) > 0, f"{name} has no tools"


def test_result_models_importable():
    """Verify all result models can be imported."""
    from shared.result_models import (
        MemorizeResult, IngestResult, HeartbeatResult,
        ConsolidateResult, DreamResult, LayerResult,
        ContextPackResult, ReminderPushResult,
        SaveConversationResult, SearchResult,
        AddMemoryResult, SaveDecisionResult,
        ThinkingResult, PlanResult,
    )
    r = MemorizeResult(memory_id="test", layer="L1", scope="session")
    assert r.status == "stored"
    assert r.model_json_schema()["type"] == "object"
