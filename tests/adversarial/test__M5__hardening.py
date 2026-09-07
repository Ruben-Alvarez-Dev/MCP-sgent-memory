"""Adversarial hardening suite — M5 audit findings (H2/H3/M3/H5/M2).

Attacker model (one drill per audit finding):

  H2 — L0_capture.heartbeat traversal: agent_id="../../pwn" must raise
        ScopeError BEFORE any filesystem touch, and nothing may appear
        outside the L1 heartbeat jail (tmp_path is the world; the jail is
        the only legal parent).
  H3 — L3_decisions identity + containment: a server bound to director-1
        must refuse to save/search/list under engineer-1 (ScopeError, no
        .md written); delete_decision on a path under _scopes/<foreign>/
        must raise ScopeError and leave the file untouched. Also covers the
        classic prefix bug: a sibling directory sharing the root's prefix
        ("decisions-evil" vs "decisions") is NOT contained.
  M3 — Lx_reasoning absolute/dot thread ids: "/tmp/pwn"-style ids feed
        _save/_load/_staging which build filesystem paths — they must raise
        ValueError and create zero files (sanitize.py allows '/' by design,
        so the gate lives at the consumer).
  H5 — L2_conversations.get_conversation cross-scope read: a thread stored
        under agent_scope="director-1" must be "not_found" for a server
        bound as engineer-1 (no existence oracle); own + shared stay
        readable, and genuinely missing threads keep the same shape.

Recipe (same as the M4 identity suite): each server module is exec'd under
a UNIQUE module name with DATA_DIR/scope paths pointed INSIDE tmp_path and
identity env vars stripped (deterministic open-mode boot); the module's
IDENTITY is then swapped for a bound Identity via monkeypatch. Storage
never touches the real data tree.
"""
from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.identity import AGENT_ID_ENV, AGENT_TOKEN_ENV, IDENTITY_MODE_ENV, Identity
from shared.scope import ScopeError

IDENTITY_ENV_VARS = (IDENTITY_MODE_ENV, AGENT_ID_ENV, AGENT_TOKEN_ENV)


def _load_server(rel: str, env: dict[str, str], tmp_path: Path, monkeypatch):
    """Exec a server main.py under a unique name with tmp-scoped env.

    Identity vars are removed FIRST so the import-time bind_identity() is
    deterministically open-mode; tests that need a bound server swap the
    module's IDENTITY afterwards (harness-bound identity, M4 contract).
    """
    for k in IDENTITY_ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    name = f"_m5_harden_{rel.replace('/', '_').replace('.py', '').lower()}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── H2: L0_capture.heartbeat traversal ──────────────────────────────


class TestH2HeartbeatTraversal:
    async def test_traversal_agent_id_rejected_nothing_outside_jail(self, tmp_path, monkeypatch):
        jail = tmp_path / "l1-working" / "agents"
        l0 = _load_server("L0_capture/server/main.py", {"L1_WORKING_PATH": str(jail)}, tmp_path, monkeypatch)

        with pytest.raises(ScopeError):
            await l0.heartbeat(agent_id="../../pwn")

        # Zero files anywhere in the world: the traversal target (tmp/pwn.json
        # via jail/../../pwn.json) and any stray heartbeat alike.
        assert list(tmp_path.rglob("pwn*")) == [], "traversal wrote files outside the jail"
        assert not (tmp_path / "pwn.json").exists()

        # Positive control: a well-formed agent_id still lands INSIDE the jail.
        res = await l0.heartbeat(agent_id="agent-ok")
        assert res.status == "active"
        assert (jail / "agent-ok.json").exists()


# ── H3: L3_decisions identity + containment ─────────────────────────


class TestH3DecisionsIdentityAndContainment:
    def _dec(self, tmp_path, monkeypatch):
        return _load_server(
            "L3_decisions/server/main.py",
            {"L3_DECISIONS_PATH": str(tmp_path / "decisions")},
            tmp_path,
            monkeypatch,
        )

    async def test_save_search_list_reject_foreign_scope_when_bound(self, tmp_path, monkeypatch):
        dec = self._dec(tmp_path, monkeypatch)
        monkeypatch.setattr(dec, "IDENTITY", Identity(agent_id="director-1", mode="bound"))

        with pytest.raises(ScopeError, match="identity-bound as 'director-1'"):
            await dec.save_decision("Spoof", content="x", scope="engineer-1")
        assert list((tmp_path / "decisions").rglob("*.md")) == [], "foreign-scope write reached disk"

        with pytest.raises(ScopeError, match="identity-bound"):
            await dec.search_decisions("spoof", agent_scope="engineer-1")
        with pytest.raises(ScopeError, match="identity-bound"):
            await dec.list_decisions(scope="engineer-1")

        # Positive control: the bound scope itself still works (default coerces).
        res = await dec.save_decision("Own", content="x", scope="default")
        assert res.status == "saved"
        assert res.file_path.startswith(str(tmp_path / "decisions"))

    async def test_delete_decision_foreign_scope_rejected_file_untouched(self, tmp_path, monkeypatch):
        dec = self._dec(tmp_path, monkeypatch)
        foreign = tmp_path / "decisions" / "_scopes" / "engineer-1" / "general" / "secret.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("---\ntitle: secret\n---\n", encoding="utf-8")
        monkeypatch.setattr(dec, "IDENTITY", Identity(agent_id="director-1", mode="bound"))

        with pytest.raises(ScopeError, match="foreign scope 'engineer-1'"):
            await dec.delete_decision(str(foreign))
        assert foreign.exists(), "foreign-scope delete destroyed the file"

        # Own scope still deletable (containment + ownership pass).
        own = tmp_path / "decisions" / "_scopes" / "director-1" / "general" / "own.md"
        own.parent.mkdir(parents=True)
        own.write_text("x", encoding="utf-8")
        assert (await dec.delete_decision(str(own)))["status"] == "deleted"

    async def test_prefix_sibling_directory_is_not_contained(self, tmp_path, monkeypatch):
        """Legacy startswith bug: '/x/decisions-evil' vs jail '/x/decisions'."""
        dec = self._dec(tmp_path, monkeypatch)
        monkeypatch.setattr(dec, "IDENTITY", Identity(agent_id="director-1", mode="bound"))
        sibling = tmp_path / "decisions-evil" / "escape.md"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("x", encoding="utf-8")

        # get_decision: soft forbidden (read-only legacy contract) …
        res = await dec.get_decision(str(sibling))
        assert res["status"] == "forbidden"
        # … delete_decision: fail-closed ScopeError, destructive calls never soften.
        with pytest.raises(ScopeError, match="escapes jail"):
            await dec.delete_decision(str(sibling))
        assert sibling.exists()


# ── M3: Lx_reasoning unsafe thread ids ──────────────────────────────


class TestM3UnsafeThreadIds:
    async def test_absolute_thread_id_rejected_no_file_created(self, tmp_path, monkeypatch):
        jail = tmp_path / "Lx-deliberative" / "sessions"
        escape = tmp_path / "outside"
        lx = _load_server(
            "Lx_reasoning/server/main.py",
            {"LX_DELIBERATIVE_PATH": str(jail), "TMP_PATH": str(tmp_path / "staging")},
            tmp_path,
            monkeypatch,
        )

        # Absolute id pointing OUTSIDE the jail (the "/tmp/pwn" finding).
        with pytest.raises(ValueError, match="unsafe session/thread id"):
            await lx.record_thought(session_id=str(escape / "pwn"), thought="stolen")
        assert not escape.exists(), "absolute thread id created a directory outside the jail"
        assert not jail.exists() or list(jail.rglob("step_*.json")) == []

        # The literal shape from the finding, through a second consumer.
        with pytest.raises(ValueError):
            await lx.get_thinking_session("/tmp/pwn")
        assert not Path("/tmp/pwn").exists()

        # Dot-prefixed ids are equally rejected (hidden-file escape hatch).
        with pytest.raises(ValueError):
            await lx.record_thought(session_id=".hidden", thought="x")

        # Positive control: a plain id still saves inside the jail.
        await lx.record_thought(session_id="think-ok", thought="fine")
        assert (jail / "think-ok" / "step_0001.json").exists()


# ── H5: L2_conversations.get_conversation cross-scope read ──────────


class TestH5GetConversationCrossScope:
    @staticmethod
    def _thread(scope: str) -> dict:
        return {
            "thread_id": "t-1",
            "agent_scope": scope,
            "summary": "",
            "created_at": "",
            "updated_at": "",
            "message_count": 1,
            "messages": [{"seq": 1, "role": "user", "content": "director-only secret"}],
        }

    async def test_foreign_thread_not_found_for_bound_caller(self, tmp_path, monkeypatch):
        l2 = _load_server("L2_conversations/server/main.py", {}, tmp_path, monkeypatch)
        monkeypatch.setattr(l2, "IDENTITY", Identity(agent_id="engineer-1", mode="bound"))

        # Foreign tenant's thread: identical shape to a missing thread — no leak.
        monkeypatch.setattr(l2, "get_thread", lambda tid: self._thread("director-1"))
        res = await l2.get_conversation("t-1")
        assert res == {"status": "not_found", "thread_id": "t-1"}
        assert "secret" not in str(res)

        # Own scope: readable.
        monkeypatch.setattr(l2, "get_thread", lambda tid: self._thread("engineer-1"))
        assert (await l2.get_conversation("t-1"))["agent_scope"] == "engineer-1"

        # Public scope: readable.
        monkeypatch.setattr(l2, "get_thread", lambda tid: self._thread("shared"))
        assert (await l2.get_conversation("t-1"))["agent_scope"] == "shared"

        # Genuinely missing: unchanged contract.
        monkeypatch.setattr(l2, "get_thread", lambda tid: None)
        assert await l2.get_conversation("nope") == {"status": "not_found", "thread_id": "nope"}
