import sys
import pytest
import json
from pathlib import Path

# Add src to pythonpath
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sequential_thinking.server import main as seq_main

# --- Test Fixtures ---

@pytest.fixture
def mock_model_packs_path(monkeypatch, tmp_path):
    mock_path = tmp_path / "data/engram/model-packs"
    mock_path.mkdir(parents=True)
    monkeypatch.setattr(seq_main, "MODEL_PACKS_PATH", mock_path)
    (mock_path / "default.json").write_text('{"name": "default", "roles": {"coder": {"temperature": 0.1}, "planner": {"temperature": 0.7}}}')
    (mock_path / "deterministic.json").write_text('{"name": "deterministic", "roles": {"coder": {"temperature": 0.0}, "planner": {"temperature": 0.4}}}')
    return mock_path

# --- Unit Tests (SPEC-2.3: Sequential Thinking with Model Packs) ---

@pytest.mark.asyncio
async def test_sequential_thinking_uses_default_pack(mock_model_packs_path):
    plan_json = await seq_main.sequential_thinking("test problem")
    plan = json.loads(plan_json)
    assert plan[0]["temperature"] == 0.7
    assert plan[1]["temperature"] == 0.1

@pytest.mark.asyncio
async def test_sequential_thinking_uses_custom_pack(mock_model_packs_path):
    plan_json = await seq_main.sequential_thinking("test problem", model_pack="deterministic")
    plan = json.loads(plan_json)
    assert plan[0]["temperature"] == 0.4
    assert plan[1]["temperature"] == 0.0

@pytest.mark.asyncio
async def test_sequential_thinking_handles_missing_pack(mock_model_packs_path):
    plan_json = await seq_main.sequential_thinking("test problem", model_pack="nonexistent")
    plan = json.loads(plan_json)
    assert plan[1]["temperature"] == 0.1
