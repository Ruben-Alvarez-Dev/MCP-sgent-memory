"""M3/M6 adversarial — L5 degradation behavior.

M3 established that L5 degrades to hash-vectors on embedding outage.
M6 removes embeddings entirely — L5 now uses FTS5-only retrieval.

This test verifies:
  1. push_reminder works without embedding backend
  2. detect_context_shift works without embedding backend
  3. No crashes when embedding is unavailable (because it's removed)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestL5NoEmbedding:
    """M6: L5 works without any embedding backend."""

    @pytest.mark.asyncio
    async def test_push_reminder_works_without_embedding(self, tmp_path):
        """push_reminder succeeds without embedding (FTS5-only)."""
        from L5_routing.server import main as l5_mod
        from shared.memory_db import MemoryDB
        
        db = MemoryDB(str(tmp_path / "test.db"), "test", 1024)
        await db.ensure_collection()
        await db.upsert("p1", {
            "content": "JWT authentication middleware",
            "agent_scope": "shared",
            "layer": 1,
        })
        
        # Monkeypatch db
        l5_mod.store = db
        
        # push_reminder should work without embedding
        result = await l5_mod.push_reminder(
            query="auth users",
            reason="test",
            agent_id="shared"
        )
        assert result.status == "reminder_pushed"

    @pytest.mark.asyncio
    async def test_detect_context_shift_works_without_embedding(self, tmp_path):
        """detect_context_shift succeeds without embedding."""
        from L5_routing.server import main as l5_mod
        from shared.memory_db import MemoryDB
        
        db = MemoryDB(str(tmp_path / "test.db"), "test", 1024)
        await db.ensure_collection()
        
        l5_mod.store = db
        
        # Should not crash
        result = await l5_mod.detect_context_shift(
            current_query="new topic",
            previous_query="old topic",
            agent_id="shared"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_request_context_works_without_embedding(self, tmp_path):
        """request_context returns results via FTS5."""
        from L5_routing.server import main as l5_mod
        from shared.memory_db import MemoryDB
        
        db = MemoryDB(str(tmp_path / "test.db"), "test", 1024)
        await db.ensure_collection()
        await db.upsert("p1", {
            "content": "AuthService JWT authentication",
            "agent_scope": "shared",
            "layer": 1,
        })
        
        l5_mod.store = db
        
        result = await l5_mod.request_context(
            query="JWT auth",
            agent_id="shared"
        )
        assert result is not None
