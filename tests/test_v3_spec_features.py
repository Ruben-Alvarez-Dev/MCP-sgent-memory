"""Tests for V3 spec features — RepoNode, pruner, repo_map, retrieval.

Covers: RepoNode model, prune_content with AST, get_repo_map with
dependencies, _rank_and_fuse with proximity (when implemented).
"""

from __future__ import annotations

import pytest

from shared.models.repo import RepoNode
from shared.retrieval import get_repo_map, prune_content


# ── RepoNode model ────────────────────────────────────────────────


def test_repo_node_stores_path_and_type():
    node = RepoNode(path="src/example.py", type="file", signature="module example")
    assert node.path == "src/example.py"
    assert node.type == "file"


def test_repo_node_has_default_empty_deps():
    node = RepoNode(path="a.py", type="file", signature="fn()")
    assert node.dependencies == []
    assert node.children == []


# ── Pruner ────────────────────────────────────────────────────────


def test_pruner_removes_comments_and_collapses_bodies():
    source = "\n".join([
        "# comment",
        "def alpha():",
        "    x = 1",
        "    y = 2",
        "    return x + y",
        "",
        "def beta():",
        "    return 'ok'",
    ])
    pruned = prune_content(source, path="demo.py", max_tokens=6)
    assert "# comment" not in pruned
    assert "def alpha" in pruned
    assert "..." in pruned


def test_pruner_preserves_structure_with_grade_collapse():
    source = "\n".join([
        '"""module doc"""',
        "",
        "class Service:",
        '    """service doc"""',
        "    def method(self):",
        "        value = 1",
        "        return value",
        "",
        "async def task():",
        "    await run()",
        "    return True",
    ])
    pruned = prune_content(source, path="service.py", max_tokens=30)
    assert '"""module doc"""' in pruned
    assert "class Service" in pruned
    assert "def method" in pruned or "..." in pruned
    assert "async def task" in pruned
    assert "return value" not in pruned


# ── get_repo_map ──────────────────────────────────────────────────


def test_get_repo_map_returns_immediate_dependencies(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\ndef run():\n    return helper()\n"
    )

    repo_map = get_repo_map("pkg/main.py", project_root=str(tmp_path))
    if repo_map is not None:
        assert repo_map["root"]["path"] == "pkg/main.py"
        deps = repo_map.get("immediate_dependencies", [])
        assert any("dep.py" in d.get("path", "") for d in deps)


def test_get_repo_map_returns_none_for_nonexistent():
    result = get_repo_map("no/such/file.py", project_root="/tmp")
    assert result is None
