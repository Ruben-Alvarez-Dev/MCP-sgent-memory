"""obsidian-kb-pipeline: KBEngine — captura, promoción, jail, reconcile."""
from __future__ import annotations

import json
import os
import time

import pytest

from shared.kb import KBEngine
from shared.memory_db import MemoryDB


@pytest.fixture()
def kb(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("MEMORY_OBSIDIAN_VAULT", str(vault))
    for k in ("MEMORY_KB_INBOX", "MEMORY_KB_WIKI", "MEMORY_KB_IMPORTANCE",
              "MEMORY_KB_MIN_AGE_DAYS", "MEMORY_KB_MAX_PER_RUN"):
        monkeypatch.delenv(k, raising=False)
    mdb = MemoryDB(str(tmp_path / "memory.db"), "kb_test", 1024)
    return KBEngine(mdb), mdb, vault


async def _seed(db, pid, content, importance=0.9, age_days=5, mem_type="gotcha"):
    created = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - age_days * 86400))
    await db.upsert(pid, {"memory_id": pid, "content": content, "importance": importance,
                          "mem_type": mem_type, "agent_scope": "shared", "agent": "pi-agent",
                          "created_at": created}, sparse=None)


async def test_capture_lands_in_inbox_with_frontmatter(kb):
    engine, db, vault = kb
    await _seed(db, "k1", "FastMCP captura call_tool en init; interceptar via ToolManager.")
    r = engine.promote_pending()
    assert len(r["captured"]) == 1 and "/00 Inbox/" in r["captured"][0]
    note = open(r["captured"][0]).read()
    assert "source: memory:k1" in note and "estado: captura" in note
    assert "tags: [memoria, origin/agent, gotcha]" in note


async def test_promotion_to_wiki_draft_with_template(kb):
    engine, db, vault = kb
    await _seed(db, "k1", "FastMCP captura call_tool en init del bridge del servidor.")
    r = engine.promote_pending()
    assert len(r["promoted"]) == 1 and "/20 Wiki/Borradores-agente/" in r["promoted"][0]
    txt = open(r["promoted"][0]).read()
    assert "estado: borrador-agente" in txt
    assert "## Concepto en 3 líneas" in txt  # conforma la plantilla del usuario
    assert "verificado: false" in txt


async def test_low_importance_skipped(kb):
    engine, db, vault = kb
    await _seed(db, "k2", "apunte menor sin valor para la wiki", importance=0.3)
    r = engine.promote_pending()
    assert r["captured"] == [] and r["skipped"] == 1


async def test_promotion_idempotent(kb):
    engine, db, vault = kb
    await _seed(db, "k1", "contenido persistente para idempotencia total")
    first = engine.promote_pending()
    assert first["captured"]
    second = engine.promote_pending()
    assert second["captured"] == [] and second["promoted"] == []


async def test_jail_blocks_path_traversal(kb):
    engine, db, vault = kb
    with pytest.raises(PermissionError):
        engine._jail(engine.vault / "../../etc/passwd")


async def test_reconcile_survives_human_move(kb, tmp_path):
    engine, db, vault = kb
    await _seed(db, "k1", "nota que el humano movera a su wiki personal")
    r = engine.promote_pending()
    wiki_note = r["promoted"][0]
    # el humano mueve la nota dentro del vault (cura moviendo)
    human_path = vault / "20 Wiki" / "mi-nota-refinada.md"
    os.replace(wiki_note, human_path)
    rec = engine.reconcile()
    assert rec["reconciled"] >= 1
    idx = json.loads((vault / engine.inbox / ".memory-index.json").read_text())
    paths = [e["path"] for e in (idx["k1"] if isinstance(idx["k1"], list) else [idx["k1"]])]
    assert str(human_path) in paths, f"el move humano no se re-rastreó: {paths}"


async def test_integrity_check_scoped(kb):
    engine, db, vault = kb
    await _seed(db, "k1", "contenido verificado por integridad")
    engine.promote_pending()
    ic = engine.integrity_check()
    assert ic["enabled"] and ic["passed"] and ic["notes"] >= 1


async def test_disabled_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMORY_OBSIDIAN_VAULT", raising=False)
    mdb = MemoryDB(str(tmp_path / "memory.db"), "kb_test", 1024)
    engine = KBEngine(mdb)
    assert not engine.enabled
    assert engine.promote_pending() == {"enabled": False}
