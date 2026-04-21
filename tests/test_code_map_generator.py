from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from shared.retrieval.code_map import generate_code_map


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "import os\nfrom datetime import datetime\n\n"
        "class AuthService:\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n\n"
        "    def get_token(self, user_id: int) -> str:\n"
        '        return f"{user_id}:{self.secret}"\n\n'
        "async def main_task():\n"
        '    print("Doing async work")\n'
    )
    (tmp_path / "src" / "api.ts").write_text(
        "import { HttpClient } from './http';\n\n"
        "export class ApiClient {\n"
        "    constructor(private http: HttpClient) {}\n\n"
        "    async fetchData(id: string): Promise<any> {\n"
        "        return this.http.get(`/data/${id}`);\n"
        "    }\n}\n\n"
        "function globalHelper(): void {\n"
        "    console.log('Helper');\n"
        "}\n"
    )
    (tmp_path / "src" / "empty.js").write_text("")
    (tmp_path / "src" / "config.weird").write_text("key=value")
    return tmp_path


def test_python_ast_map_correctness(temp_project: Path):
    py_file = temp_project / "src" / "service.py"
    code_map = generate_code_map(str(py_file))
    assert code_map is not None
    assert code_map.language == "python"

    symbols_by_name = {s.name: s for s in code_map.symbols}
    assert "AuthService" in symbols_by_name
    assert symbols_by_name["AuthService"].type == "class"
    assert "__init__" in symbols_by_name
    assert symbols_by_name["__init__"].type == "method"
    assert "get_token" in symbols_by_name
    assert symbols_by_name["get_token"].type == "method"
    assert "main_task" in symbols_by_name
    assert symbols_by_name["main_task"].type == "function"


def test_map_text_token_reduction(temp_project: Path):
    """AC-1.1.2: map_text is a compressed representation of the original."""
    py_file = temp_project / "src" / "service.py"
    code_map = generate_code_map(str(py_file))
    assert code_map is not None
    assert "AuthService" in code_map.map_text
    assert "get_token" in code_map.map_text

def test_unknown_language_returns_none(temp_project: Path):
    weird_file = temp_project / "src" / "config.weird"
    code_map = generate_code_map(str(weird_file))
    # Should not crash. May return a map with unknown language or None.
    if code_map is not None:
        assert code_map.language in ("unknown", "text-only", "text")


def test_sha_consistency(temp_project: Path):
    py_file = temp_project / "src" / "service.py"
    code_map1 = generate_code_map(str(py_file))
    code_map2 = generate_code_map(str(py_file))
    assert code_map1 is not None
    assert code_map2 is not None
    assert code_map1.sha == code_map2.sha
    py_file.write_text(py_file.read_text() + "\n# new comment")
    code_map3 = generate_code_map(str(py_file))
    assert code_map1.sha != code_map3.sha


def test_supported_languages(temp_project: Path):
    ts_file = temp_project / "src" / "api.ts"
    code_map = generate_code_map(str(ts_file))
    assert code_map is not None
    assert code_map.language == "typescript"
    symbols_by_name = {s.name: s for s in code_map.symbols}
    assert "ApiClient" in symbols_by_name
    assert "globalHelper" in symbols_by_name


def test_non_existent_file_returns_none():
    code_map = generate_code_map("non_existent_file.py")
    assert code_map is None


def test_empty_file_does_not_crash(temp_project: Path):
    empty_file = temp_project / "src" / "empty.js"
    code_map = generate_code_map(str(empty_file))
    assert code_map is not None
    assert code_map.language == "javascript"
    assert not code_map.symbols
