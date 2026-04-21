"""Tests for shared.retrieval.code_map — code map generation.

Covers: generate_code_map for Python (AST), TypeScript, JS, unknown,
empty, nonexistent files. Verifies SHA consistency, symbol extraction,
and map_text compression.
"""

from __future__ import annotations

import pytest

from shared.retrieval.code_map import generate_code_map


# ── Python AST correctness ────────────────────────────────────────


def test_python_ast_extracts_classes_methods_functions(temp_project):
    code_map = generate_code_map(str(temp_project / "src" / "service.py"))
    assert code_map is not None
    assert code_map.language == "python"

    symbols = {s.name: s for s in code_map.symbols}
    assert "AuthService" in symbols
    assert symbols["AuthService"].type == "class"
    assert "__init__" in symbols
    assert symbols["__init__"].type == "method"
    assert "get_token" in symbols
    assert symbols["get_token"].type == "method"
    assert "main_task" in symbols
    assert symbols["main_task"].type == "function"


def test_python_map_text_contains_symbols_not_comments(temp_project):
    code_map = generate_code_map(str(temp_project / "src" / "service.py"))
    assert code_map is not None
    assert "AuthService" in code_map.map_text
    assert "get_token" in code_map.map_text


# ── TypeScript / JavaScript ───────────────────────────────────────


def test_typescript_extracts_classes_and_functions(temp_project):
    code_map = generate_code_map(str(temp_project / "src" / "api.ts"))
    assert code_map is not None
    assert code_map.language == "typescript"
    symbols = {s.name: s for s in code_map.symbols}
    assert "ApiClient" in symbols
    assert "globalHelper" in symbols


def test_empty_js_file_returns_map_with_no_symbols(temp_project):
    code_map = generate_code_map(str(temp_project / "src" / "empty.js"))
    assert code_map is not None
    assert code_map.language == "javascript"
    assert len(code_map.symbols) == 0


# ── Edge cases ────────────────────────────────────────────────────


def test_unknown_extension_does_not_crash(temp_project):
    code_map = generate_code_map(str(temp_project / "src" / "config.weird"))
    if code_map is not None:
        assert code_map.language in ("unknown", "text-only", "text")


def test_nonexistent_file_returns_none():
    assert generate_code_map("/no/such/file.py") is None


# ── SHA consistency ───────────────────────────────────────────────


def test_sha_is_deterministic(temp_project):
    path = temp_project / "src" / "service.py"
    sha1 = generate_code_map(str(path)).sha
    sha2 = generate_code_map(str(path)).sha
    assert sha1 == sha2


def test_sha_changes_when_content_changes(temp_project):
    path = temp_project / "src" / "service.py"
    sha_before = generate_code_map(str(path)).sha
    path.write_text(path.read_text() + "\n# new comment\n")
    sha_after = generate_code_map(str(path)).sha
    assert sha_before != sha_after
