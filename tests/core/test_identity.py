"""M4 core identity tests — registry, token verification, boot binding, policy.

Traceability: ISO-01, ISO-13, ISO-14, ISO-15 (openspec/changes/M4-identidad).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat

import pytest

from shared.identity import (
    AGENT_ID_ENV,
    AGENT_TOKEN_ENV,
    IDENTITY_MODE_ENV,
    AgentRegistry,
    IdentityError,
    bind_identity,
)
from shared.scope import ScopeError


@pytest.fixture()
def reg_path(tmp_path):
    return str(tmp_path / "agents.json")


@pytest.fixture()
def reg(reg_path):
    return AgentRegistry(reg_path)


@pytest.fixture()
def clean_env(monkeypatch):
    for k in (IDENTITY_MODE_ENV, AGENT_ID_ENV, AGENT_TOKEN_ENV):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ── ISO-13: registry ─────────────────────────────────────────────────


@pytest.mark.unit
def test_register_roundtrip(reg):
    token = reg.register("director-1")
    assert token and len(token) >= 32
    assert reg.verify("director-1", token) is True
    assert reg.verify("director-1", token + "x") is False
    assert reg.verify("director-1", "") is False


@pytest.mark.unit
def test_registry_stores_hash_only(reg, reg_path):
    token = reg.register("director-1")
    with open(reg_path) as fh:
        data = json.load(fh)
    entry = data["director-1"]
    assert entry["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(data)                      # plaintext never stored
    mode = stat.S_IMODE(os.stat(reg_path).st_mode)
    assert mode == 0o600                                      # owner-only


@pytest.mark.unit
def test_cross_agent_replay_rejected(reg):
    t1 = reg.register("director-1")
    reg.register("engineer-1")
    assert reg.verify("engineer-1", t1) is False              # id+token are a pair
    assert reg.verify("director-1", t1) is True


@pytest.mark.unit
def test_unknown_agent_and_reserved_rejected(reg):
    assert reg.verify("ghost", "any-token") is False
    with pytest.raises(ScopeError):
        reg.register("global")                                # reserved
    with pytest.raises(ScopeError):
        reg.register("../../etc")                             # traversal


@pytest.mark.unit
def test_corrupt_registry_starts_empty(reg_path, caplog):
    with open(reg_path, "w") as fh:
        fh.write("{corrupt")
    r2 = AgentRegistry(reg_path)
    assert r2.list_agents() == {}                             # WARN + empty, no crash


@pytest.mark.unit
def test_rotation_invalidates_old_token(reg):
    t1 = reg.register("director-1")
    reg.register("director-1")                                # rotate
    assert reg.verify("director-1", t1) is False


# ── ISO-14: strict fail-closed boot ──────────────────────────────────


@pytest.mark.unit
def test_strict_without_credentials_fails(clean_env):
    env = {IDENTITY_MODE_ENV: "strict"}  # no credentials → fail-closed
    with pytest.raises(IdentityError):
        bind_identity(env=env, registry=AgentRegistry(os.devnull))


@pytest.mark.unit
def test_strict_with_bad_token_fails(clean_env, reg):
    reg.register("director-1")
    env = {
        IDENTITY_MODE_ENV: "strict",
        AGENT_ID_ENV: "director-1",
        AGENT_TOKEN_ENV: "wrong-token",
    }
    with pytest.raises(IdentityError):
        bind_identity(env=env, registry=reg)


@pytest.mark.unit
def test_partial_credentials_fail(clean_env, reg):
    reg.register("director-1")
    env = {IDENTITY_MODE_ENV: "strict", AGENT_ID_ENV: "director-1"}
    with pytest.raises(IdentityError):
        bind_identity(env=env, registry=reg)


@pytest.mark.unit
def test_invalid_mode_fails(clean_env, reg):
    with pytest.raises(IdentityError):
        bind_identity(env={IDENTITY_MODE_ENV: "yolo"}, registry=reg)


# ── Binding + ISO-15 policy ──────────────────────────────────────────


@pytest.mark.unit
def test_open_mode_when_unconfigured(clean_env, reg):
    ident = bind_identity(env={}, registry=reg)
    assert ident.mode == "open" and ident.agent_id == "shared"


@pytest.mark.unit
def test_credentials_bind_even_in_open_mode(clean_env, reg):
    token = reg.register("director-1")
    ident = bind_identity(
        env={AGENT_ID_ENV: "director-1", AGENT_TOKEN_ENV: token}, registry=reg
    )
    assert ident.mode == "bound" and ident.agent_id == "director-1"


@pytest.mark.unit
def test_assert_agent_bound_policy(clean_env, reg):
    token = reg.register("director-1")
    ident = bind_identity(
        env={AGENT_ID_ENV: "director-1", AGENT_TOKEN_ENV: token}, registry=reg
    )
    assert ident.assert_agent("default") == "director-1"      # ISO-15 coercion
    assert ident.assert_agent("shared") == "shared"           # public stays public
    assert ident.assert_agent("director-1") == "director-1"   # own
    with pytest.raises(ScopeError):
        ident.assert_agent("engineer-1")                      # foreign → rejected
    with pytest.raises(ScopeError):
        ident.assert_agent("../../etc")                       # shape still validated


@pytest.mark.unit
def test_assert_agent_open_validates_shape_only(clean_env, reg):
    ident = bind_identity(env={}, registry=reg)
    assert ident.assert_agent("engineer-1") == "engineer-1"   # legacy: allowed
    with pytest.raises(ScopeError):
        ident.assert_agent("../x")                            # shape enforced
