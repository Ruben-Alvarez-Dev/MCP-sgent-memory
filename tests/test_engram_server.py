import sys
import pytest
import json
from pathlib import Path

# Add src to pythonpath
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engram.server import main as engram_main

# --- Test Fixtures ---

@pytest.fixture
def mock_engram_path(monkeypatch, tmp_path):
    """Mocks the paths used by the engram server to use a temporary directory."""
    mock_packs_path = tmp_path / "data/memory/engram/model-packs"
    mock_packs_path.mkdir(parents=True)
    monkeypatch.setattr(engram_main, "MODEL_PACKS_PATH", mock_packs_path)
    
    # Create a default pack for testing
    (mock_packs_path / "default.json").write_text('{"name": "default", "roles": {"coder": {"temperature": 0.1}}}')
    (mock_packs_path / "creative.json").write_text('{"name": "creative", "roles": {"planner": {"temperature": 0.9}}}')
    
    return mock_packs_path

# --- Unit Tests (SPEC-2.2, Refactored for JSON) ---

@pytest.mark.asyncio
async def test_get_model_pack_success(mock_engram_path):
    pack_json_str = await engram_main.get_model_pack("default")
    pack = json.loads(pack_json_str)
    assert pack["name"] == "default"
    assert pack["roles"]["coder"]["temperature"] == 0.1

@pytest.mark.asyncio
async def test_get_model_pack_fallback(mock_engram_path):
    pack_json_str = await engram_main.get_model_pack("nonexistent")
    pack = json.loads(pack_json_str)
    assert pack["name"] == "default-fallback"

@pytest.mark.asyncio
async def test_list_model_packs(mock_engram_path):
    packs_json_str = await engram_main.list_model_packs()
    packs = json.loads(packs_json_str)
    assert len(packs) == 2
    assert "default" in packs
    assert "creative" in packs

@pytest.mark.asyncio
async def test_set_model_pack_success(mock_engram_path):
    new_pack_json = '{"name": "experimental", "roles": {"coder": {"temperature": 0.0}}}'
    result_json_str = await engram_main.set_model_pack("experimental", new_pack_json)
    result = json.loads(result_json_str)
    
    assert result["status"] == "saved"
    new_file = Path(result["file"])
    assert new_file.exists()
    assert new_file.name == "experimental.json"
    assert new_file.read_text() == new_pack_json

@pytest.mark.asyncio
async def test_set_model_pack_invalid_json(mock_engram_path):
    invalid_json = '{"name": "bad", "roles": }' # Invalid JSON
    result_json_str = await engram_main.set_model_pack("bad", invalid_json)
    result = json.loads(result_json_str)
    
    assert result["status"] == "error"
    assert "Expecting value" in result["message"]
    assert not (mock_engram_path / "bad.json").exists()
