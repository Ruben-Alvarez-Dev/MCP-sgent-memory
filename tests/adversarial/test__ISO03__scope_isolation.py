"""Adversarial scope-isolation matrix — M1-lite (ISO-03/ISO-04/ISO-09/ISO-10).

Runs in CI, zero external services (filesystem only).

STATUS A1–A16 (security-auditor matrix):
  GREEN now : A1 (reminders), A2-analog (decisions), A4-shape (invalid scope),
              A7-shape (traversal), A8-shape (reserved spoof), A9-shape (no glob)
  PENDING   : A3 falsified-vs-harness identity (M4), A5/A6 facts engine filter (M2),
              A10 arbitrary collection map (M2), A11/A12/A16 trunk workflow (M5),
              A14 timing oracle measurement (M2), A15 legacy consolidated (M2).
Pending items are explicit TODOs with owners — never silent gaps.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.scope import (
    ScopeError,
    assert_contained,
    iter_namespaced_files,
    normalize_scope,
    scope_dir_hashed,
    visible_dirs_hashed,
)

# ── ISO-09: canonical scope ──────────────────────────────────────────


class TestNormalizeScope:
    @pytest.mark.parametrize("s", ["shared", "default", "agent-a", "director-1", "x", "a" * 32, "Agent_A-9"])
    def test_valid(self, s):
        assert normalize_scope(s) == s.strip().lower()

    @pytest.mark.parametrize(
        "s",
        ["", "   ", "../../etc", "..", "a/b", "*", "c1/p*", "a b", "a" * 33,
         "global", "merged", "consolidated", "narrative", "dream", "GLOBAL",
         "a\x00b", "sí", "a.b", "a:b", "-lead", "_x"],
    )
    def test_invalid_rejected(self, s):
        with pytest.raises(ScopeError):
            normalize_scope(s)

    def test_non_string_rejected(self):
        with pytest.raises(ScopeError):
            normalize_scope(None)  # type: ignore[arg-type]

    def test_no_fallback_to_global(self):
        """Invalid scope must raise, never silently become shared/global."""
        for bad in ["", "global", "../x"]:
            try:
                normalize_scope(bad)
            except ScopeError:
                continue
            raise AssertionError(f"{bad!r} did not raise")


class TestScopeDirs:
    def test_hashed_dir_never_embeds_caller_text(self, tmp_path):
        d = scope_dir_hashed(tmp_path, "director-1")
        assert d.parent == tmp_path
        assert "director" not in d.name  # opaque hex only

    def test_traversal_cannot_escape(self, tmp_path):
        with pytest.raises(ScopeError):
            scope_dir_hashed(tmp_path, "../../etc")

    def test_visible_dirs_never_siblings(self, tmp_path):
        dirs = visible_dirs_hashed(tmp_path, "agent-a")
        assert len(dirs) == 2  # own + shared
        # create a sibling namespace and prove it is not listed
        scope_dir_hashed(tmp_path, "agent-b").mkdir(parents=True)
        names = {d.name for d in dirs}
        sib = scope_dir_hashed(tmp_path, "agent-b").name
        assert sib not in names

    def test_assert_contained_blocks_escape(self, tmp_path):
        jail = tmp_path / "jail"
        jail.mkdir()
        with pytest.raises(ScopeError):
            assert_contained(jail / ".." / "outside.txt", jail)

    def test_iter_excludes_scopes_from_shared_walk(self, tmp_path):
        (tmp_path / "pub.md").write_text("public decision")
        priv = tmp_path / "_scopes" / "agent-a"
        priv.mkdir(parents=True)
        (priv / "priv.md").write_text("private decision")
        shared_files = {p.name for p in iter_namespaced_files(tmp_path, "shared")}
        assert shared_files == {"pub.md"}
        own_files = {p.name for p in iter_namespaced_files(tmp_path, "agent-a")}
        assert own_files == {"pub.md", "priv.md"}
        other_files = {p.name for p in iter_namespaced_files(tmp_path, "agent-b")}
        assert other_files == {"pub.md"}


# ── ISO-03: reminders (A1) ──────────────────────────────────────────


def _make_reminder():
    from shared.models import ContextPack, ContextReminder

    return ContextReminder(pack=ContextPack(request_id="t", query="q"))


class TestRemindersIsolation:
    def test_a1_cross_agent_read_denied(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", True)
        l5._save_reminder(_make_reminder(), "agent-a")
        assert l5._get_reminders("agent-b") == []
        assert len(l5._get_reminders("agent-a")) == 1

    def test_shared_visible_to_all(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", True)
        l5._save_reminder(_make_reminder(), "shared")
        assert len(l5._get_reminders("agent-a")) == 1
        assert len(l5._get_reminders("agent-b")) == 1
        assert len(l5._get_reminders("shared")) == 1

    def test_invalid_agent_rejected(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", True)
        for bad in ["", "../../etc", "*", "global"]:
            with pytest.raises(ScopeError):
                l5._get_reminders(bad)

    def test_dismiss_is_scoped(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", True)
        r = _make_reminder()
        l5._save_reminder(r, "agent-a")
        res = asyncio.run(l5.dismiss_reminder(r.reminder_id, "agent-b"))
        assert res.status == "not_found"
        assert len(l5._get_reminders("agent-a")) == 1  # untouched
        res = asyncio.run(l5.dismiss_reminder(r.reminder_id, "agent-a"))
        assert res.status == "dismissed"
        assert l5._get_reminders("agent-a") == []

    def test_legacy_root_files_migrate_to_shared(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", False)
        legacy = tmp_path / "legacy.json"
        legacy.write_text(_make_reminder().model_dump_json())
        seen = l5._get_reminders("agent-a")
        assert len(seen) == 1  # visible as shared, not as agent-a private
        assert not legacy.exists()  # moved, not copied

    def test_check_reminders_tool_scoped(self, tmp_path, monkeypatch):
        import L5_routing.server.main as l5

        monkeypatch.setattr(l5, "_L5_selective_path", tmp_path)
        monkeypatch.setattr(l5, "_migrated_legacy", True)
        l5._save_reminder(_make_reminder(), "agent-a")
        res = asyncio.run(l5.check_reminders("agent-b"))
        assert res.count == 0
        res = asyncio.run(l5.check_reminders("agent-a"))
        assert res.count == 1


# ── ISO-04: decisions (A2) ──────────────────────────────────────────


def _decision_entities(*words):
    from shared.llm.config import QueryIntent

    return QueryIntent(
        intent_type="decision_recall",
        entities=list(words),
        scope="this_project",
        time_window="all",
        needs_external=False,
        needs_ranking=False,
        needs_consolidation=False,
    )


class TestDecisionsIsolation:
    def test_a2_private_decision_hidden_from_sibling(self, tmp_path, monkeypatch):
        import L3_decisions.server.main as dec

        monkeypatch.setattr(dec, "DECISIONS_PATH", tmp_path)
        res = asyncio.run(dec.save_decision("Auth Choice", content="usamos autenticacion oauth", scope="agent-a"))
        assert res.status == "saved"
        assert "_scopes" in res.file_path
        # direct tool search
        r_b = asyncio.run(dec.search_decisions("autenticacion", agent_scope="agent-b"))
        assert r_b.count == 0
        r_a = asyncio.run(dec.search_decisions("autenticacion", agent_scope="agent-a"))
        assert r_a.count == 1
        # list wiring (previously decorative scope param)
        l_b = asyncio.run(dec.list_decisions(scope="agent-b"))
        assert l_b.count == 0
        l_a = asyncio.run(dec.list_decisions(scope="agent-a"))
        assert l_a.count == 1

    def test_shared_decision_visible_to_all(self, tmp_path, monkeypatch):
        import L3_decisions.server.main as dec

        monkeypatch.setattr(dec, "DECISIONS_PATH", tmp_path)
        res = asyncio.run(dec.save_decision("Shared Choice", content="usamos sqlite", scope="shared"))
        assert "_scopes" not in res.file_path
        assert asyncio.run(dec.search_decisions("sqlite", agent_scope="agent-z")).count == 1

    def test_traversal_scope_rejected_no_write(self, tmp_path, monkeypatch):
        import L3_decisions.server.main as dec

        monkeypatch.setattr(dec, "DECISIONS_PATH", tmp_path)
        res = asyncio.run(dec.save_decision("Evil", content="x", scope="../../etc"))
        assert res.status == "error"
        assert list(tmp_path.rglob("Evil*")) == []

    def test_retrieval_path_forwards_scope(self, tmp_path, monkeypatch):
        """_retrieve_parallel MUST forward agent_scope to _retrieve_L3_decisions."""
        import shared.retrieval as ret

        seen = {}

        async def fake_hybrid(intent, k, level=None, collection=None, agent_scope="shared"):
            return []

        async def fake_decisions(intent, k, agent_scope="shared"):
            seen["scope"] = agent_scope
            return []

        monkeypatch.setattr(ret, "_retrieve_hybrid", fake_hybrid)
        monkeypatch.setattr(ret, "_retrieve_L3_decisions", fake_decisions)
        intent = _decision_entities("AuthService")
        asyncio.run(ret._retrieve_parallel(intent, ret.PROFILES["default"], "engineer-1"))
        assert seen.get("scope") == "engineer-1"

    def test_retrieval_decisions_namespaced(self, tmp_path, monkeypatch):
        import shared.retrieval as ret

        monkeypatch.setattr(ret, "L3_DECISIONS_PATH", str(tmp_path))
        shared_f = tmp_path / "s.md"
        shared_f.write_text("usamos postgres para todo")
        priv_d = tmp_path / "_scopes" / "agent-a"
        priv_d.mkdir(parents=True)
        (priv_d / "p.md").write_text("usamos sqlite secreto")
        intent = _decision_entities("sqlite")
        got_b = asyncio.run(ret._retrieve_L3_decisions(intent, 5, "agent-b"))
        assert all("secreto" not in i.content for i in got_b)
        got_a = asyncio.run(ret._retrieve_L3_decisions(intent, 5, "agent-a"))
        assert any("secreto" in i.content for i in got_a)
