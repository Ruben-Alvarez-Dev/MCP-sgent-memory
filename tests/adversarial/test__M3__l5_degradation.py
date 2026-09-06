"""Adversarial degradation matrix — M3 (RET-06 / KNOWN-BUG-002).

Proves L5 tools NEVER raise on an embedding outage: _embed_or_hash degrades
to the deterministic SHA-256 hash-vector (shared.memory_db.hash_vector).
Adversarial stance:

  RET-06.a — push_reminder under outage (async_embed raises ConnectionError
             IN the l5 module) returns status="reminder_pushed" with
             sources > 0, scored via the ENGINE hash path (score_source="hash")
             against a NULL-vector seeded row. Real validated query — no
             validate_push_reminder mock. tmp DATA_DIR set BEFORE import
             (unique module name via importlib) so nothing touches real data.
  RET-06.b — detect_context_shift(equal texts) under outage -> similarity
             exactly 1.0 (deterministic hash), shift_detected False.
  RET-06.c — detect_context_shift(different texts) under outage -> sim < 1.0
             (distinct deterministic hashes).

Core (non-adversarial) counterparts: tests/core/test_mcp_modules.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation, pytest.mark.req("RET-06")]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.memory_db import hash_vector

QUERY = "kubernetes pod eviction policy in production clusters"


async def _load_l5(tmp_path: Path, monkeypatch) -> object:
    """Import L5 server main.py under a UNIQUE module name with tmp dirs.

    Env vars are set BEFORE exec_module so the module-level Config.from_env()
    and MemoryDB(None -> default_db_path()) resolve inside tmp_path —
    env_loader only sets defaults for vars not already present, so the
    monkeypatched values win and no test writes to the real data tree.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L5_SELECTIVE_PATH", str(tmp_path / "L5-selective" / "reminders"))
    name = f"_l5_m3_degradation_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC / "L5_routing" / "server" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    # Production parity: the points table exists (created at server startup);
    # the shifted branch of detect_context_shift searches the store.
    await mod.store.ensure_collection()
    return mod


async def _outage(l5, monkeypatch) -> None:
    """Make async_embed fail IN the l5 module (RET-06 outage condition)."""
    async def _explode(text: str):
        raise ConnectionError("embedding server unreachable")

    monkeypatch.setattr(l5, "async_embed", _explode)


async def _seed_null_vector_row(l5) -> None:
    """Seed one shared row with vector=NULL -> engine scores it via hash."""
    await l5.store.ensure_collection()
    await l5.store.upsert(
        "m3-ret06-seed-shared",
        None,  # NULL vector: query-time hash-vector scoring (STO-05)
        {"content": QUERY, "agent_scope": "shared", "layer": 2, "type": "fact"},
    )


class TestPushReminderOutage:
    async def test_push_reminder_degrades_to_hash_and_pushes(self, tmp_path, monkeypatch):
        l5 = await _load_l5(tmp_path, monkeypatch)
        await _outage(l5, monkeypatch)
        await _seed_null_vector_row(l5)

        res = await l5.push_reminder(query=QUERY, reason="ret-06 outage drill", agent_id="default")

        assert res.status == "reminder_pushed"
        assert res.sources > 0  # found via deterministic hash-vector query
        # The scored source came from the ENGINE hash path, not dense vectors.
        hits = await l5.store.search(
            hash_vector(QUERY, l5.config.embedding_dim),
            limit=5,
            score_threshold=l5.config.L5_routing_min_score,
            filter={"must": [{"key": "agent_scope", "match": {"any": ["default", "shared"]}}]},
        )
        assert any(h["score_source"] == "hash" for h in hits)
        # Reminder persisted inside tmp_path only (no leakage to real data dir).
        rid = res.reminder_id
        written = list((tmp_path / "L5-selective" / "reminders").rglob("*.json"))
        assert written, "reminder file must be written under tmp L5_SELECTIVE_PATH"
        assert rid in json.loads(written[0].read_text())["reminder_id"]


class TestContextShiftOutage:
    async def test_equal_texts_similarity_one_no_shift(self, tmp_path, monkeypatch):
        l5 = await _load_l5(tmp_path, monkeypatch)
        await _outage(l5, monkeypatch)

        res = await l5.detect_context_shift(current_query=QUERY, previous_query=QUERY)

        assert res.shift_detected is False
        assert res.similarity == 1.0  # identical deterministic hash vectors

    async def test_different_texts_similarity_below_one(self, tmp_path, monkeypatch):
        l5 = await _load_l5(tmp_path, monkeypatch)
        await _outage(l5, monkeypatch)

        res = await l5.detect_context_shift(
            current_query="rust borrow checker lifetimes",
            previous_query="kubernetes pod eviction policy",
        )

        assert res.similarity < 1.0  # distinct deterministic hashes
