import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

# Add src to pythonpath
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.retrieval.index_repo import _build_code_map_points, upsert_repository_index
from shared.retrieval.code_map import CodeMap

# --- Mocks and Fixtures ---

@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Creates a temporary project structure for testing."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "main.py").write_text("import os\n\ndef run():\n    print('Hello')")
    (tmp_path / "utils.js").write_text("export function helper() { return 1; }")
    (tmp_path / "README.md").write_text("# My Project")
    (tmp_path / "config.txt").write_text("key=val") # Should be ignored by suffix filter
    return tmp_path

@pytest.mark.asyncio
async def test_build_code_map_points_structure(temp_project: Path):
    """Verifies the structure and content of generated Qdrant points."""
    
    async def mock_embed_fn(text: str):
        return [0.1] * 5

    points = await _build_code_map_points(str(temp_project), mock_embed_fn)

    assert len(points) == 3 # .py, .js, .md files

    py_point = next((p for p in points if p["payload"]["file_path"].endswith("main.py")), None)
    assert py_point is not None
    assert py_point["vector"] == [0.1] * 5
    assert py_point["payload"]["type"] == "code_map"
    assert py_point["payload"]["language"] == "python"
    assert "run" in py_point["payload"]["content"]
    assert "os" in py_point["payload"]["imports"]

@pytest.mark.asyncio
async def test_upsert_repository_index_calls_client(temp_project: Path):
    """Verifies that upsert_repository_index calls the httpx client correctly."""
    
    mock_client = AsyncMock()
    mock_client.put.return_value = MagicMock(status_code=200)
    mock_client.put.return_value.raise_for_status = MagicMock()

    async def mock_embed_fn(text: str):
        return [0.2] * 5

    await upsert_repository_index(
        project_root=str(temp_project),
        qdrant_url="http://localhost:6333",
        collection="test_collection",
        client=mock_client,
        embed_fn=mock_embed_fn
    )

    mock_client.put.assert_called_once()
    call_args = mock_client.put.call_args
    assert "/collections/test_collection/points" in call_args.args[0]
    
    points_in_call = call_args.kwargs["json"]["points"]
    assert len(points_in_call) == 3
    assert points_in_call[0]["vector"] == [0.2] * 5
    
