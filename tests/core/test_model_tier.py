"""Tests for shared/model_tier.py — no external services required.

Covers: tier boundaries (constructed profiles), override precedence,
reactive downgrade with injected reachability, persistence roundtrip
validated by hand against hardware-profile.schema.json (v1.0).
"""
import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared import model_tier
from shared.config import Config
from shared.llm.base import LLMUnavailableError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Neutralize ambient env (config/.env may be loaded by other tests)."""
    for var in ["MODEL_TIER", "MODEL_TIER_TTL"] + [
        f"ROLE_MODEL_{r.upper()}" for r in model_tier.ROLES
    ]:
        monkeypatch.delenv(var, raising=False)


# ── Helpers: constructed profiles, no probes ───────────────────────────

def _hw(total=16.0, available=8.0, gpu="none", os_name="darwin", arch="x86_64"):
    return {
        "hostname": "test-host",
        "os": os_name,
        "arch": arch,
        "cpu": "Test CPU",
        "logical_cores": 8,
        "ram_total_gb": total,
        "ram_available_gb": available,
        "gpu_class": gpu,
    }


def _backends(ollama=True, llama_server=False, llama_cpp=False, models=()):
    backend_map = model_tier.BackendMap(
        ollama=model_tier.BackendStatus(
            reachable=ollama, url="http://127.0.0.1:11434",
            detail=None if ollama else "ConnectError",
        ),
        llama_server=model_tier.BackendStatus(reachable=llama_server),
        llama_cpp_local=model_tier.BackendStatus(reachable=llama_cpp),
    )
    return backend_map, list(models)


def _resolver(tmp_path, hw=None, ttl=3600.0):
    cfg = Config(
        server_dir=str(tmp_path),
        data_dir=str(tmp_path / "data"),
        L0_events_jsonl=str(tmp_path / "data" / "events.jsonl"),
    )
    resolver = model_tier.TierResolver(config=cfg, ttl_seconds=ttl)
    resolver._probe_hardware = lambda: dict(hw or _hw())
    resolver._probe_backends = lambda: _backends()
    return resolver


# ── Tier boundaries (pure decide_tier) ─────────────────────────────────

class TestTierBoundaries:
    def test_no_backend_is_t0_regardless_of_ram(self):
        tier, reason = model_tier.decide_tier("apple_silicon", 128.0, 100.0, any_llm_backend=False)
        assert tier == "T0"
        assert "no LLM backend" in reason

    def test_below_6gb_available_is_t1(self):
        tier, _ = model_tier.decide_tier("none", 16.0, 5.99, any_llm_backend=True)
        assert tier == "T1"

    def test_exactly_6gb_available_is_t2(self):
        tier, _ = model_tier.decide_tier("none", 16.0, 6.0, any_llm_backend=True)
        assert tier == "T2"

    def test_low_available_beats_high_total(self):
        # 64 GB machine under memory pressure still drops to T1
        tier, _ = model_tier.decide_tier("discrete", 64.0, 4.0, any_llm_backend=True)
        assert tier == "T1"

    def test_32gb_total_is_t3(self):
        tier, _ = model_tier.decide_tier("none", 32.0, 20.0, any_llm_backend=True)
        assert tier == "T3"

    def test_just_below_32gb_total_is_t2(self):
        tier, _ = model_tier.decide_tier("none", 31.9, 20.0, any_llm_backend=True)
        assert tier == "T2"

    def test_apple_silicon_24gb_unified_is_t3(self):
        tier, _ = model_tier.decide_tier("apple_silicon", 24.0, 16.0, any_llm_backend=True)
        assert tier == "T3"

    def test_x86_24gb_is_only_t2(self):
        tier, _ = model_tier.decide_tier("none", 24.0, 16.0, any_llm_backend=True)
        assert tier == "T2"

    def test_64gb_with_accelerator_is_t4(self):
        tier, _ = model_tier.decide_tier("apple_silicon", 64.0, 48.0, any_llm_backend=True)
        assert tier == "T4"

    def test_64gb_cpu_only_is_t3_not_t4(self):
        tier, _ = model_tier.decide_tier("none", 64.0, 48.0, any_llm_backend=True)
        assert tier == "T3"


# ── Role→model matrix ──────────────────────────────────────────────────

class TestRoleModels:
    def test_t2_matrix_defaults(self):
        rm, _ = model_tier.resolve_role_models("T2", [], ollama_reachable=False)
        assert rm.embedding == "qwen3-embedding:0.6b"
        assert rm.reranker == "qwen3-reranker:0.6b"
        assert rm.small == "qwen3.5:2b"
        assert rm.primary == "qwen3.5:4b"
        assert rm.coordinator is None

    def test_t0_has_no_models(self):
        rm, _ = model_tier.resolve_role_models("T0", [], ollama_reachable=False)
        assert rm.primary is None and rm.small is None and rm.embedding is None

    def test_t4_enables_coordinator(self):
        rm, notes = model_tier.resolve_role_models("T4", [], ollama_reachable=False)
        assert rm.coordinator is not None
        assert any("coordinator" in n for n in notes)

    def test_primary_degrades_to_qwen25_when_qwen35_not_pulled(self):
        rm, notes = model_tier.resolve_role_models(
            "T2", ["qwen2.5:7b", "bge-m3:latest"], ollama_reachable=True
        )
        assert rm.primary == "qwen2.5:7b"
        assert any("degraded" in n for n in notes)

    def test_primary_stays_qwen35_when_available(self):
        rm, notes = model_tier.resolve_role_models(
            "T2", ["qwen3.5:4b", "qwen2.5:7b"], ollama_reachable=True
        )
        assert rm.primary == "qwen3.5:4b"
        assert not any("degraded" in n for n in notes)


# ── Override precedence ────────────────────────────────────────────────

class TestOverrides:
    def test_model_tier_env_forces_tier(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_TIER", "t1")
        profile = _resolver(tmp_path).resolve()  # hardware says T2
        assert profile.tier == "T1"
        assert "MODEL_TIER" in (profile.tier_reason or "")

    def test_model_tier_auto_uses_probe(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_TIER", "auto")
        assert _resolver(tmp_path).resolve().tier == "T2"

    def test_invalid_model_tier_falls_back_to_auto(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_TIER", "t9")
        assert _resolver(tmp_path).resolve().tier == "T2"

    def test_role_model_env_wins_over_defaults(self, monkeypatch):
        monkeypatch.setenv("ROLE_MODEL_PRIMARY", "custom:1b")
        rm, _ = model_tier.resolve_role_models("T2", [], ollama_reachable=False)
        assert rm.primary == "custom:1b"

    def test_role_model_env_wins_over_degradation(self, monkeypatch):
        monkeypatch.setenv("ROLE_MODEL_PRIMARY", "custom:1b")
        rm, _ = model_tier.resolve_role_models(
            "T2", ["qwen2.5:7b"], ollama_reachable=True
        )
        assert rm.primary == "custom:1b"


# ── Cache, TTL and triggers ────────────────────────────────────────────

class TestCacheAndTriggers:
    def test_ttl_cache_and_force_refresh(self, tmp_path):
        resolver = _resolver(tmp_path, ttl=3600.0)
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            return _backends()

        resolver._probe_backends = probe
        resolver.resolve()
        resolver.resolve()
        assert calls["n"] == 1  # cached
        resolver.force_refresh()
        assert calls["n"] == 2
        assert resolver.maybe_refresh() is None  # TTL not expired
        assert calls["n"] == 2

    def test_maybe_refresh_reprobes_after_ttl(self, tmp_path):
        resolver = _resolver(tmp_path, ttl=0.0)  # always expired
        resolver.resolve()
        assert resolver.maybe_refresh() is not None

    def test_reactive_downgrade_to_t0(self, tmp_path, caplog):
        state = {"up": True}
        resolver = _resolver(tmp_path, ttl=3600.0)
        resolver._probe_backends = lambda: _backends(ollama=state["up"])

        assert resolver.resolve().tier == "T2"

        state["up"] = False
        with caplog.at_level(logging.WARNING, logger="agent-memory.model_tier"):
            profile = resolver.notify_backend_failure("ollama")

        assert profile.tier == "T0"
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("Tier transition" in m for m in messages)
        assert any("T2" in m and "T0" in m for m in messages)

        # Transition also lands in the L0 audit trail as a system event
        events_path = tmp_path / "data" / "events.jsonl"
        assert events_path.exists()
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        assert any(e["source"] == "model_tier" and e["type"] == "system" for e in events)

    def test_preferred_backend_prefers_ollama_then_llama_cpp(self, tmp_path):
        resolver = _resolver(tmp_path)
        assert resolver.preferred_llm_backend() == "ollama"

        resolver._probe_backends = lambda: _backends(ollama=False, llama_cpp=True)
        resolver.force_refresh()
        assert resolver.preferred_llm_backend() == "llama_cpp"

    def test_preferred_backend_raises_at_t0(self, tmp_path):
        resolver = _resolver(tmp_path)
        resolver._probe_backends = lambda: _backends(ollama=False)
        resolver.force_refresh()
        with pytest.raises(LLMUnavailableError):
            resolver.preferred_llm_backend()


# ── Persistence roundtrip (hand-validated against the JSON Schema) ────

SCHEMA_REQUIRED = [
    "schema_version", "probed_at", "os", "arch", "cpu", "logical_cores",
    "ram_total_gb", "ram_available_gb", "gpu_class", "backends", "tier",
]
SCHEMA_ALLOWED = set(SCHEMA_REQUIRED) | {"hostname", "models_available", "tier_reason", "role_models"}
BACKEND_KEYS = {"ollama", "llama_server", "llama_cpp_local"}
ROLE_KEYS = {"embedding", "reranker", "small", "primary", "coordinator"}


class TestPersistence:
    def test_roundtrip_conforms_to_schema(self, tmp_path):
        resolver = _resolver(tmp_path)
        resolver.resolve()

        path = tmp_path / "data" / "system" / "hardware-profile.json"
        assert path.exists()
        data = json.loads(path.read_text())

        # required fields present
        for key in SCHEMA_REQUIRED:
            assert key in data, f"missing required field {key}"
        # additionalProperties: false
        assert set(data) <= SCHEMA_ALLOWED
        assert data["schema_version"] == "1.0"
        assert data["tier"] in ("T0", "T1", "T2", "T3", "T4")
        assert data["os"] in ("darwin", "linux", "windows")
        assert data["arch"] in ("arm64", "x86_64", "other")
        assert data["gpu_class"] in ("apple_silicon", "discrete", "integrated", "none")
        assert isinstance(data["logical_cores"], int) and data["logical_cores"] >= 1

        # backends: all three required, each with reachable, no extra keys
        assert set(data["backends"]) == BACKEND_KEYS
        for status in data["backends"].values():
            assert isinstance(status["reachable"], bool)
            assert set(status) <= {"reachable", "url", "detail"}

        # role_models: subset of known roles; coordinator may be null
        assert set(data["role_models"]) <= ROLE_KEYS
        for role, value in data["role_models"].items():
            if role == "coordinator":
                assert value is None or isinstance(value, str)
            else:
                assert isinstance(value, str)

        # roundtrip back into the pydantic model
        profile = model_tier.HardwareProfile.model_validate(data)
        assert profile.tier == data["tier"]

    def test_atomic_write_leaves_no_tmp_file(self, tmp_path):
        resolver = _resolver(tmp_path)
        resolver.resolve()
        system_dir = tmp_path / "data" / "system"
        assert not list(system_dir.glob("*.tmp"))

    def test_record_outcome_appends_jsonl(self, tmp_path):
        resolver = _resolver(tmp_path)
        resolver.record_outcome("summarize", "qwen2.5:7b", True)
        resolver.record_outcome("rank", "qwen3.5:2b", False)

        path = tmp_path / "data" / "system" / "routing-outcomes.jsonl"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(lines) == 2
        assert lines[0] == {"ts": lines[0]["ts"], "task": "summarize", "model": "qwen2.5:7b", "ok": True}
        assert lines[1]["ok"] is False
