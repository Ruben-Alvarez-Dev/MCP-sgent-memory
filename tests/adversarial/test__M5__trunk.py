"""M5 adversarial — trunk workflow (A11/A12/A16), LLM-free compliance, sidecar token.

All cases run filesystem-only (no daemons, no ports). Sidecar token gate is
exercised at the handler-helper level by design (no sockets in CI).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "src"))

pytestmark = [pytest.mark.isolation]

from shared.memory_db import MemoryDB, ScopeError  # noqa: E402
from shared.identity import Identity  # noqa: E402


def _vec(seed: float) -> list[float]:
    v = [seed] * 8
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(BASE / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── A11: automatism cannot write the trunk ───────────────────────────


async def test_a11_consolidation_autoplacement_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(exist_ok=True)
    db = MemoryDB(str(tmp_path / "data" / "memory.db"), "L0_L4_memory", 8)
    db._ensure_schema()
    # the old automatic promotion shape (scope merged, no approval triple)
    with pytest.raises(ScopeError):
        await db.upsert("auto-1", _vec(1.0), {"content": "auto promotion", "agent_scope": "merged"})
    # with the flag but without the human triple — still blocked
    with pytest.raises(ScopeError):
        await db.upsert("auto-2", _vec(1.0), {"content": "auto promotion", "agent_scope": "merged"},
                        allow_reserved_scope=True)
    hits = await db.scroll({"must": [{"key": "agent_scope", "match": {"value": "merged"}}]})
    assert hits == []


# ── A12: trunk rows always carry provenance ──────────────────────────


async def test_a12_merged_rows_carry_provenance_by_construction(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(exist_ok=True)
    db = MemoryDB(str(tmp_path / "data" / "memory.db"), "L0_L4_memory", 8)
    db._ensure_schema()
    # every legitimate way in requires the triple; write one properly
    await db.upsert("t1", None, {"content": "approved", "agent_scope": "merged",
                                 "approved_by": "manu",
                                 "provenance": [{"from_scope": "shared", "point_id": "s1"}]},
                    allow_reserved_scope=True)
    rows = db._conn.execute(
        "SELECT payload FROM points WHERE agent_scope='merged'"
    ).fetchall()
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload"])
    assert payload.get("approved_by") == "manu"
    assert payload.get("provenance") and payload["provenance"][0]["point_id"] == "s1"


# ── A16: merged is readable by every agent ───────────────────────────


async def test_a16_trunk_public_read(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(exist_ok=True)
    db = MemoryDB(str(tmp_path / "data" / "memory.db"), "L0_L4_memory", 8)
    db._ensure_schema()
    await db.upsert("t1", _vec(0.8), {"content": "common knowledge", "agent_scope": "merged",
                                      "approved_by": "manu",
                                      "provenance": [{"from_scope": "shared", "point_id": "x"}]},
                    allow_reserved_scope=True)
    for agent in ["director-1", "engineer-1", "qa-bot"]:
        hits = await db.search(
            _vec(0.8), limit=10, score_threshold=-1.0,
            filter={"must": [{"key": "agent_scope", "match": {"any": [agent, "shared", "merged"]}}]},
        )
        assert any(h["id"] == "t1" for h in hits)


# ── approve_promotion tool contract ──────────────────────────────────


async def test_approve_promotion_tool_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    l04 = _load("L04_m5", "src/L0_to_L4_consolidation/server/main.py")
    await l04.db.ensure_collection()

    await l04.db.upsert("s1", None, {"content": "source fact", "agent_scope": "shared", "layer": 3})
    result = await l04.approve_promotion('["s1"]', approved_by="manu")
    assert result["merged_id"].startswith("merged-")
    assert result["approved_by"] == "manu"

    # no human identity → rejected
    assert "error" in await l04.approve_promotion('["s1"]', approved_by="  ")
    # unknown source → rejected
    assert "error" in await l04.approve_promotion('["ghost"]', approved_by="manu")
    # merged row carries provenance
    row = await l04.db.get(result["merged_id"])
    assert row["payload"]["provenance"][0]["point_id"] == "s1"
    assert row["payload"]["approved_by"] == "manu"


# ── compliance: SEMANTIC_UNVERIFIED without micro-LLM ────────────────


async def test_semantic_rules_unverified_without_llm():
    from shared.compliance import ProjectRule, verify_semantic

    rules = [ProjectRule(
        id="SR-1", description="no print statements", severity="low",
        semantic_prompt="does the code print?",
    )]
    violations = await verify_semantic("print('hi')", rules=rules)
    assert len(violations) == 1
    assert "SEMANTIC_UNVERIFIED" in violations[0].detail
    assert violations[0].severity in ("info", "low")


# ── ISO-17: sidecar token gate ───────────────────────────────────────


def test_sidecar_token_gate(monkeypatch):
    import shared.api_server as api

    class _FakeHeaders(dict):
        def get(self, k, default=None):
            return super().get(k, default)

    monkeypatch.delenv("MEMORY_HTTP_TOKEN", raising=False)
    assert api._check_http_token(_FakeHeaders()) is True          # unset = localhost trust

    monkeypatch.setenv("MEMORY_HTTP_TOKEN", "sekrit")
    assert api._check_http_token(_FakeHeaders()) is False                          # missing
    assert api._check_http_token(_FakeHeaders({"X-Memory-Token": "wrong"})) is False
    assert api._check_http_token(_FakeHeaders({"X-Memory-Token": "sekrit"})) is True
