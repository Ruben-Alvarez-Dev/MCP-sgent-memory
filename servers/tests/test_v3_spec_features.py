from __future__ import annotations

import importlib.util
import asyncio
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.models.repo import RepoNode
from shared.retrieval import get_repo_map, prune_content
import shared.retrieval as retrieval


def test_repo_node_model_exists():
    node = RepoNode(path="src/example.py", type="file", signature="module example")
    assert node.path == "src/example.py"
    assert node.type == "file"


def test_pruner_removes_comments_and_collapses_python_bodies():
    source = "\n".join(
        [
            "# comment",
            "def alpha():",
            "    x = 1",
            "    y = 2",
            "    return x + y",
            "",
            "def beta():",
            "    return 'ok'",
        ]
    )

    pruned = prune_content(source, path="demo.py", max_tokens=6)

    assert "# comment" not in pruned
    assert "def alpha()" in pruned
    assert "..." in pruned


def test_pruner_keeps_python_structure_with_ast_grade_collapse():
    source = "\n".join(
        [
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
        ]
    )

    pruned = prune_content(source, path="service.py", max_tokens=30)

    assert '"""module doc"""' in pruned
    assert "class Service:" in pruned
    assert '"""service doc"""' in pruned
    assert "def method(self):" in pruned
    assert "async def task():" in pruned
    assert "return value" not in pruned
    assert "await run()" not in pruned
    assert pruned.count("...") >= 2


def test_get_repo_map_returns_immediate_dependencies(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "dep.py").write_text("def helper():\n    return 1\n")
    (pkg / "main.py").write_text(
        "from pkg.dep import helper\n\n"
        "def run():\n"
        "    return helper()\n"
    )

    repo_map = get_repo_map("pkg/main.py", project_root=str(tmp_path))

    assert repo_map is not None
    assert repo_map["root"]["path"] == "pkg/main.py"
    assert any(dep["path"] == "pkg/dep.py" for dep in repo_map["immediate_dependencies"])


def test_sequential_thinking_stages_and_applies_change_sets(tmp_path: Path, monkeypatch):
    module_path = ROOT / "sequential_thinking" / "server" / "main.py"
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class DummyFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            def decorator(fn):
                return fn

            return decorator

        def run(self):
            return None

    fastmcp_module.FastMCP = DummyFastMCP
    sys.modules["mcp"] = types.ModuleType("mcp")
    sys.modules["mcp.server"] = types.ModuleType("mcp.server")
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

    spec = importlib.util.spec_from_file_location("sequential_thinking_main", module_path)
    sequential_main = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(sequential_main)

    monkeypatch.setattr(sequential_main, "STAGING_BUFFER_PATH", tmp_path / "staging")

    target = tmp_path / "applied.txt"
    changes = json.dumps([{"path": str(target), "content": "hola"}])

    staged = json.loads(asyncio.run(sequential_main.propose_change_set("sess-1", "demo", changes)))
    assert staged["status"] == "staged"
    assert Path(staged["staging_path"]).exists()

    waiting = json.loads(asyncio.run(sequential_main.apply_sandbox(staged["change_set_id"], approved=False)))
    assert waiting["status"] == "awaiting_approval"
    assert not target.exists()

    applied = json.loads(asyncio.run(sequential_main.apply_sandbox(staged["change_set_id"], approved=True)))
    assert applied["status"] == "applied"
    assert target.read_text() == "hola"


def test_repo_proximity_prioritizes_structurally_closer_items():
    profile = retrieval.RetrievalProfile(
        name="dev",
        level_weights={2: 1.0},
        top_k_per_level={2: 5},
        token_budget=4000,
        max_time_ms=1000,
        needs_ai_ranking=False,
    )
    intent = retrieval.QueryIntent(
        intent_type="code_lookup",
        entities=["pkg", "main", "helper"],
        scope="this_project",
        time_window="all",
        needs_external=False,
        needs_ranking=False,
        needs_consolidation=False,
    )
    close_item = retrieval.ContextItem(
        content="def helper()",
        source_level=2,
        source_name="qdrant",
        score=0.8,
        entities=["helper"],
        timestamp=None,
        metadata={"path": "pkg/main.py", "dependencies": ["pkg.dep"]},
    )
    far_item = retrieval.ContextItem(
        content="totally unrelated symbol",
        source_level=2,
        source_name="qdrant",
        score=0.85,
        entities=["other"],
        timestamp=None,
        metadata={"path": "docs/notes.py", "dependencies": []},
    )

    ranked = retrieval._rank_and_fuse({"L2": [far_item, close_item]}, profile, intent)

    assert ranked[0].metadata["path"] == "pkg/main.py"
