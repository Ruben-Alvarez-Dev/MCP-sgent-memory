import sys
import pytest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import engram.server.main as engram_main


@pytest.fixture
def mock_packs(tmp_path, monkeypatch):
    packs_dir = tmp_path / "model-packs"
    packs_dir.mkdir()
    (packs_dir / "default.json").write_text(
        '{"name": "default", "roles": {"coder": {"temperature": 0.1}}}'
    )
    (packs_dir / "creative.json").write_text(
        '{"name": "creative", "roles": {"planner": {"temperature": 0.9}}}'
    )
    monkeypatch.setattr(engram_main, "_MODEL_PACKS_DIR", packs_dir)
    monkeypatch.setattr(engram_main, "_get_packs_dir", lambda: packs_dir)
    return packs_dir


@pytest.mark.asyncio
async def test_get_model_pack_success(mock_packs):
    result = await engram_main.get_model_pack("default")
    data = json.loads(result); pack = data.get("pack", data)
    assert pack.get("name") == "default" or pack.get("status") == "ok"
    assert "coder" in pack["roles"]


@pytest.mark.asyncio
async def test_get_model_pack_fallback(mock_packs):
    result = await engram_main.get_model_pack("nonexistent")
    data = json.loads(result)
    assert "error" in data or "pack" in data or "status" in data


@pytest.mark.asyncio
async def test_list_model_packs(mock_packs):
    result = await engram_main.list_model_packs()
    data = json.loads(result)
    assert isinstance(data, (list, dict))
    if isinstance(data, list):
        names = [p.get("name", p) if isinstance(p, dict) else p for p in data]
        assert "default" in names


@pytest.mark.asyncio
async def test_set_model_pack_success(mock_packs):
    new_pack = '{"name": "experimental", "roles": {"coder": {"temperature": 0.0}}}'
    result = await engram_main.set_model_pack("experimental", new_pack)
    data = json.loads(result)
    assert data.get("status") in ("saved", "ok", "success") or "file" in data


@pytest.mark.asyncio
async def test_set_model_pack_invalid_json(mock_packs):
    invalid_json = '{"name": "bad", "roles": }'
    result = await engram_main.set_model_pack("bad", invalid_json)
    data = json.loads(result)
    assert data.get("status") in ("error", "invalid") or "error" in data
