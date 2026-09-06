"""Adversarial identity suite — M4 (ISO-01 / ISO-13 / ISO-14 / ISO-15).

Attacker model: a compromised/harness-external caller tries to make a server
bound to one scope act on another, replay a foreign token pair, or boot the
server into an unverified state. Adversarial stance:

  A17 — SCOOF (scope spoof): identity bound to director-1 must reject
        agent_id="engineer-1" with ScopeError BEFORE any I/O — both on the
        Identity object and on the REAL L5 tools (push_reminder /
        check_reminders), with storage replaced by tripwires that fail the
        test if touched. DATA_DIR/L5_SELECTIVE_PATH are tmp and set BEFORE
        the unique-name importlib exec (same recipe as the M3 suite); the
        module's IDENTITY is then swapped for a bound Identity. Credentials
        are ALWAYS passed as explicit env dicts to bind_identity — never
        via os.environ.
  A18 — strict boot is fail-closed: missing or wrong credentials raise
        IdentityError; no half-bound Identity ever escapes bind_identity.
  A19 — replay cruzado: a token is bound to its agent_id; engineer-1 cannot
        replay director-1's token (hmac.compare_digest over SHA-256 only).
  A20 — open mode stays honest: legacy scopes allowed, shape validation
        still enforced ("../x" → ScopeError), and the OPEN-mode WARNING is
        observable in the log (ISO-01 declared, not silent).
  A21 — registry hardening: corrupt agents.json boots empty (no crash),
        reserved scopes ("global") are rejected, the file lands with 0600
        and the plaintext token never touches disk.

Core (non-adversarial) counterparts: tests/core/test_identity.py.
Object of study (read-only): src/shared/identity.py, src/L5_routing/server/main.py.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import stat
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation]

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.identity import (
    AGENT_ID_ENV,
    AGENT_TOKEN_ENV,
    IDENTITY_MODE_ENV,
    AgentRegistry,
    IdentityError,
    bind_identity,
)
from shared.scope import ScopeError

IDENTITY_ENV_VARS = (IDENTITY_MODE_ENV, AGENT_ID_ENV, AGENT_TOKEN_ENV)
# Valid for validate_push_reminder — the ONLY thing under test in A17's push
# path is the identity gate, so the query itself must be beyond suspicion.
VALID_QUERY = "kubernetes pod eviction policy in production clusters"


@pytest.fixture()
def reg(tmp_path) -> AgentRegistry:
    """Registry confined to tmp — bind_identity NEVER sees the default path."""
    return AgentRegistry(str(tmp_path / "agents.json"))


@pytest.fixture()
def no_identity_env(monkeypatch):
    """Strip ambient credential vars so no test can accidentally bind via os.environ."""
    for k in IDENTITY_ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _credentials(reg: AgentRegistry, agent_id: str, *, mode: str | None = "strict"):
    """Register agent and build the env dict passed EXPLICITLY to bind_identity."""
    token = reg.register(agent_id)
    env = {AGENT_ID_ENV: agent_id, AGENT_TOKEN_ENV: token}
    if mode is not None:
        env[IDENTITY_MODE_ENV] = mode
    return env, token


async def _load_l5(tmp_path: Path, monkeypatch) -> object:
    """Import L5 server main.py under a UNIQUE module name with tmp dirs.

    Env vars are set BEFORE exec_module so the module-level Config.from_env(),
    MemoryDB and bind_identity() all resolve inside tmp_path (env_loader only
    fills defaults for vars not present, so the monkeypatched values win and
    nothing touches the real data tree). Identity vars are removed first so
    the import-time bind is deterministically open-mode.
    """
    for k in IDENTITY_ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L5_SELECTIVE_PATH", str(tmp_path / "L5-selective" / "reminders"))
    name = f"_l5_m4_identity_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC / "L5_routing" / "server" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _forbid_storage(l5, monkeypatch) -> list[str]:
    """Replace every L5 storage touchpoint with a tripwire that records + explodes."""
    touched: list[str] = []

    async def _boom_store_search(*a, **k):
        touched.append("store.search")
        raise AssertionError("storage touched after identity gate: store.search called")

    def _boom_get(agent_id):
        touched.append("_get_reminders")
        raise AssertionError("storage touched after identity gate: _get_reminders called")

    def _boom_save(r, scope="shared"):
        touched.append("_save_reminder")
        raise AssertionError("storage touched after identity gate: _save_reminder called")

    monkeypatch.setattr(l5.store, "search", _boom_store_search)
    monkeypatch.setattr(l5, "_get_reminders", _boom_get)
    monkeypatch.setattr(l5, "_save_reminder", _boom_save)
    return touched


# ── A17: scope spoof against a bound identity ────────────────────────


class TestA17SpoofForeignScope:
    def test_bound_identity_rejects_foreign_scope(self, reg):
        reg.register("engineer-1")  # foreign tenant exists in the registry…
        env, _tok = _credentials(reg, "director-1")  # …but we bind as director-1
        ident = bind_identity(env=env, registry=reg)

        assert (ident.mode, ident.agent_id) == ("bound", "director-1")
        assert ident.as_dict() == {"agent_id": "director-1", "mode": "bound"}
        with pytest.raises(ScopeError, match="director-1"):
            ident.assert_agent("engineer-1")  # foreign → rejected pre-I/O
        assert ident.assert_agent("default") == "director-1"  # ISO-15 coercion
        assert ident.assert_agent("shared") == "shared"       # public stays public
        assert ident.assert_agent("director-1") == "director-1"  # own scope ok

    async def test_l5_tools_gate_before_storage(self, tmp_path, monkeypatch):
        reg = AgentRegistry(str(tmp_path / "agents.json"))
        reg.register("engineer-1")
        env, _tok = _credentials(reg, "director-1")
        ident = bind_identity(env=env, registry=reg)

        l5 = await _load_l5(tmp_path, monkeypatch)  # DATA_DIR tmp set BEFORE import
        touched = _forbid_storage(l5, monkeypatch)
        monkeypatch.setattr(l5, "IDENTITY", ident)  # harness-bound identity in

        with pytest.raises(ScopeError, match="identity-bound as 'director-1'"):
            await l5.push_reminder(query=VALID_QUERY, reason="a17 spoof drill", agent_id="engineer-1")
        with pytest.raises(ScopeError, match="identity-bound as 'director-1'"):
            await l5.check_reminders(agent_id="engineer-1")

        assert touched == [], f"storage touched after rejected spoof: {touched}"
        reminders_root = tmp_path / "L5-selective" / "reminders"
        if reminders_root.exists():
            assert list(reminders_root.rglob("*.json")) == []


# ── A18: strict boot is fail-closed ──────────────────────────────────


class TestA18StrictBootFailClosed:
    def test_strict_without_credentials_raises(self, reg, no_identity_env):
        env = {IDENTITY_MODE_ENV: "strict"}  # mode only, no credentials
        with pytest.raises(IdentityError, match="strict mode requires"):
            bind_identity(env=env, registry=reg)

    def test_strict_with_bad_token_raises(self, reg, no_identity_env):
        reg.register("director-1")
        env = {
            IDENTITY_MODE_ENV: "strict",
            AGENT_ID_ENV: "director-1",
            AGENT_TOKEN_ENV: "forged-token-from-attacker",
        }
        with pytest.raises(IdentityError, match="verification failed"):
            bind_identity(env=env, registry=reg)


# ── A19: cross-agent token replay ────────────────────────────────────


class TestA19CrossAgentReplay:
    def test_foreign_token_replay_rejected(self, reg):
        tok_director = reg.register("director-1")
        tok_engineer = reg.register("engineer-1")
        assert tok_director != tok_engineer
        assert reg.verify("engineer-1", tok_director) is False  # replay rejected
        assert reg.verify("director-1", tok_director) is True   # own pair only
        assert reg.verify("engineer-1", tok_engineer) is True
        assert reg.verify("ghost", tok_director) is False       # unknown id
        assert reg.verify("engineer-1", "") is False            # empty token


# ── A20: open mode is legacy-permissive but shape-validated and loud ──


class TestA20OpenMode:
    def test_open_bind_allows_legacy_but_validates_shape_and_warns(self, reg, caplog):
        with caplog.at_level(logging.WARNING, logger="shared.identity"):
            ident = bind_identity(env={}, registry=reg)  # no credentials at all

        assert ident.mode == "open"
        assert ident.agent_id == "shared"
        assert ident.assert_agent("engineer-1") == "engineer-1"  # legacy allowed
        with pytest.raises(ScopeError):
            ident.assert_agent("../x")                            # shape enforced
        warnings = [
            r for r in caplog.records
            if r.name == "shared.identity" and r.levelno == logging.WARNING
        ]
        assert any("OPEN mode" in r.getMessage() for r in warnings), (
            "bind_identity must WARN (ISO-01) when booting without credentials"
        )


# ── A21: registry hardening ──────────────────────────────────────────


class TestA21RegistryHardening:
    def test_corrupt_registry_boots_empty_without_crash(self, tmp_path, caplog):
        p = tmp_path / "agents.json"
        p.write_text("{corrupt json!!!", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="shared.identity"):
            r = AgentRegistry(str(p))
        assert r.list_agents() == {}                 # empty, not crashed
        assert r.verify("director-1", "any") is False  # fail-closed verify
        assert any("corrupt" in r_.getMessage() for r_ in caplog.records)

    def test_reserved_scope_rejected(self, reg):
        with pytest.raises(ScopeError, match="reserved"):
            reg.register("global")
        assert "global" not in reg.list_agents()

    def test_file_is_0600_and_never_holds_plaintext_token(self, reg, tmp_path):
        path = tmp_path / "agents.json"
        token = reg.register("director-1")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f"registry must be owner-only, got {oct(mode)}"
        raw = path.read_text(encoding="utf-8")
        assert token not in raw                     # plaintext never on disk
        data = json.loads(raw)
        assert set(data["director-1"]) == {"token_sha256", "created_at"}
        assert token.encode() not in path.read_bytes()
