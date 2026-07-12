"""Adaptive model-tier resolver — machine capability probe → tier → role models.

The same repo runs on machines with radically different capabilities
(Hackintosh x86 16 GB CPU-only, Apple Silicon studio, future >=64 GB boxes).
This module probes the machine at runtime and resolves:

    HardwareProfile (schema: openspec/specs/model-stack/hardware-profile.schema.json)
        → tier  T0 degraded | T1 edge | T2 standard | T3 workstation | T4 coordinator
        → role→model map (embedding, reranker, small, primary, coordinator)

Verification triggers (hook semantics, spec `model-stack`):
    startup   — unified server `_ensure_initialized` calls `resolve()`
    periodic  — heartbeat piggyback via `maybe_refresh()` (TTL: MODEL_TIER_TTL, 900 s)
    reactive  — `notify_backend_failure(backend)` on any backend connect failure
    on demand — `force_refresh()` from health_check / model_tier_status / API

Overrides: MODEL_TIER=auto|t0..t4 forces the tier; ROLE_MODEL_<ROLE> pins a model.

Self-contained by design: stdlib + httpx + pydantic + shared.config for paths.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from shared.config import Config

logger = logging.getLogger("agent-memory.model_tier")

SCHEMA_VERSION = "1.0"
REACHABILITY_TIMEOUT = 1.5   # seconds per backend probe
DEFAULT_TTL_SECONDS = 900.0  # MODEL_TIER_TTL default

# ── Tier thresholds (spec: openspec/specs/model-stack/spec.md) ────────
T1_MAX_AVAILABLE_GB = 6.0        # available RAM below this → T1 edge
T3_MIN_TOTAL_GB = 32.0           # total RAM at/above this → T3 workstation
T3_APPLE_MIN_TOTAL_GB = 24.0     # Apple Silicon unified memory shortcut to T3
T4_MIN_TOTAL_GB = 64.0           # total RAM + accelerator → T4 coordinator

# ── Default role→model matrix (ADR-0006, defaults for T2) ────────────
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_RERANKER_MODEL = "qwen3-reranker:0.6b"
DEFAULT_SMALL_MODEL = "qwen3.5:2b"
DEFAULT_PRIMARY_MODEL = "qwen3.5:4b"
T3_PRIMARY_MODEL = "qwen3.5:9b"          # "primary 9B class" per spec (T3/T4)
FALLBACK_PRIMARY_MODEL = "qwen2.5:7b"    # explicit degradation until qwen3.5 is pulled

ROLES = ("embedding", "reranker", "small", "primary", "coordinator")
VALID_TIERS = ("T0", "T1", "T2", "T3", "T4")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    """Repo root: parents of src/shared/model_tier.py."""
    return Path(__file__).resolve().parents[2]


# ── Profile models (mirror hardware-profile.schema.json v1.0) ─────────

class BackendStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reachable: bool
    url: str | None = None
    detail: str | None = None


class BackendMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama: BackendStatus
    llama_server: BackendStatus
    llama_cpp_local: BackendStatus


class RoleModels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding: str | None = None
    reranker: str | None = None
    small: str | None = None
    primary: str | None = None
    coordinator: str | None = None  # null unless tier == T4


class HardwareProfile(BaseModel):
    """Machine capability snapshot. Persisted at data/system/hardware-profile.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    probed_at: str
    hostname: str | None = None
    os: Literal["darwin", "linux", "windows"]
    arch: Literal["arm64", "x86_64", "other"]
    cpu: str
    logical_cores: int = Field(ge=1)
    ram_total_gb: float = Field(ge=0)
    ram_available_gb: float = Field(ge=0)
    gpu_class: Literal["apple_silicon", "discrete", "integrated", "none"]
    backends: BackendMap
    models_available: list[str] = Field(default_factory=list)
    tier: Literal["T0", "T1", "T2", "T3", "T4"]
    tier_reason: str | None = None
    role_models: RoleModels | None = None

    def to_persistable(self) -> dict:
        """Dict valid against hardware-profile.schema.json.

        Nulls are stripped (schema types are plain strings) except
        role_models.coordinator, which the schema allows as null.
        """
        data = self.model_dump(mode="json", exclude_none=True)
        if self.role_models is not None:
            rm = {
                k: v
                for k, v in self.role_models.model_dump(mode="json").items()
                if v is not None
            }
            rm["coordinator"] = self.role_models.coordinator
            data["role_models"] = rm
        return data


# ── Hardware probes (stdlib only) ──────────────────────────────────────

def _sysctl(key: str) -> str | None:
    try:
        out = subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("sysctl %s failed: %s", key, e)
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _darwin_available_gb() -> float:
    """Estimate available RAM on macOS from vm_stat (free+inactive+speculative)."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("vm_stat failed: %s", e)
        return 0.0
    if out.returncode != 0:
        return 0.0
    page_size = 4096
    m = re.search(r"page size of (\d+) bytes", out.stdout)
    if m:
        page_size = int(m.group(1))
    pages = 0
    for label in ("Pages free", "Pages inactive", "Pages speculative"):
        m = re.search(rf"{re.escape(label)}:\s+(\d+)", out.stdout)
        if m:
            pages += int(m.group(1))
    return round(pages * page_size / 1024**3, 2)


def _linux_meminfo_gb() -> tuple[float, float]:
    """(total_gb, available_gb) from /proc/meminfo."""
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("/proc/meminfo unreadable: %s", e)
        return 0.0, 0.0
    total = available = 0.0
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            total = round(int(line.split()[1]) / 1024**2, 2)
        elif line.startswith("MemAvailable:"):
            available = round(int(line.split()[1]) / 1024**2, 2)
    return total, available


def _detect_os() -> Literal["darwin", "linux", "windows"]:
    name = platform.system().lower()
    if name.startswith("darwin"):
        return "darwin"
    if name.startswith("windows"):
        return "windows"
    return "linux"


def _detect_arch() -> Literal["arm64", "x86_64", "other"]:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    return "other"


def _detect_gpu_class(os_name: str, arch: str) -> Literal["apple_silicon", "discrete", "integrated", "none"]:
    """apple_silicon on darwin+arm64; darwin x86 is treated as CPU-only.

    On linux, an NVIDIA kernel driver counts as a discrete accelerator.
    """
    if os_name == "darwin":
        return "apple_silicon" if arch == "arm64" else "none"
    if os_name == "linux" and Path("/proc/driver/nvidia/version").exists():
        return "discrete"
    return "none"


def probe_hardware() -> dict:
    """OS/RAM/CPU snapshot using stdlib probes only."""
    os_name = _detect_os()
    arch = _detect_arch()
    cpu = ""
    logical_cores = os.cpu_count() or 1
    ram_total_gb = 0.0
    ram_available_gb = 0.0

    if os_name == "darwin":
        memsize = _sysctl("hw.memsize")
        if memsize and memsize.isdigit():
            ram_total_gb = round(int(memsize) / 1024**3, 2)
        cpu = _sysctl("machdep.cpu.brand_string") or platform.processor() or arch
        ncpu = _sysctl("hw.ncpu")
        if ncpu and ncpu.isdigit():
            logical_cores = int(ncpu)
        ram_available_gb = _darwin_available_gb()
    elif os_name == "linux":
        ram_total_gb, ram_available_gb = _linux_meminfo_gb()
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8")
            m = re.search(r"model name\s*:\s*(.+)", cpuinfo)
            cpu = m.group(1).strip() if m else ""
        except OSError:
            cpu = ""
        cpu = cpu or platform.processor() or arch
    else:
        cpu = platform.processor() or arch

    return {
        "hostname": socket.gethostname(),
        "os": os_name,
        "arch": arch,
        "cpu": cpu or "unknown",
        "logical_cores": max(logical_cores, 1),
        "ram_total_gb": ram_total_gb,
        "ram_available_gb": ram_available_gb,
        "gpu_class": _detect_gpu_class(os_name, arch),
    }


# ── Backend reachability (httpx, short timeouts) ──────────────────────

def _check_ollama(url: str) -> tuple[BackendStatus, list[str]]:
    """GET {url}/api/tags — reachability + visible model tags."""
    try:
        resp = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=REACHABILITY_TIMEOUT)
    except httpx.HTTPError as e:
        return BackendStatus(reachable=False, url=url, detail=type(e).__name__), []
    if resp.status_code != 200:
        return (
            BackendStatus(reachable=False, url=url, detail=f"HTTP {resp.status_code}"),
            [],
        )
    try:
        models = [m.get("name", "") for m in resp.json().get("models", [])]
    except (ValueError, AttributeError):
        models = []
    return BackendStatus(reachable=True, url=url), [m for m in models if m]


def _check_llama_server(url: str) -> BackendStatus:
    """GET {url}/health — a running llama-server instance."""
    try:
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=REACHABILITY_TIMEOUT)
    except httpx.HTTPError as e:
        return BackendStatus(reachable=False, url=url, detail=type(e).__name__)
    if resp.status_code == 200:
        return BackendStatus(reachable=True, url=url)
    return BackendStatus(reachable=False, url=url, detail=f"HTTP {resp.status_code}")


def _check_llama_cpp_local(root: Path) -> tuple[BackendStatus, list[str]]:
    """Local llama.cpp capability: engine/bin/llama-server binary + models/*.gguf."""
    binary = root / "engine" / "bin" / "llama-server"
    ggufs = sorted(p.name for p in (root / "models").glob("*.gguf")) if (root / "models").exists() else []
    if binary.exists() and ggufs:
        return BackendStatus(reachable=True, detail=f"{len(ggufs)} gguf model(s)"), ggufs
    missing = []
    if not binary.exists():
        missing.append("engine/bin/llama-server missing")
    if not ggufs:
        missing.append("no models/*.gguf")
    return BackendStatus(reachable=False, detail="; ".join(missing)), []


# ── Tier decision (pure, unit-testable) ────────────────────────────────

def decide_tier(
    gpu_class: str,
    ram_total_gb: float,
    ram_available_gb: float,
    any_llm_backend: bool,
) -> tuple[str, str]:
    """Map capability facts to (tier, reason). Thresholds are module constants."""
    if not any_llm_backend:
        return "T0", "no LLM backend reachable — degraded (heuristic summaries only)"
    if ram_available_gb < T1_MAX_AVAILABLE_GB:
        return (
            "T1",
            f"available RAM {ram_available_gb:g} GB < {T1_MAX_AVAILABLE_GB:g} GB",
        )
    if ram_total_gb >= T4_MIN_TOTAL_GB and gpu_class != "none":
        return (
            "T4",
            f"total RAM {ram_total_gb:g} GB >= {T4_MIN_TOTAL_GB:g} GB with accelerator ({gpu_class})",
        )
    if ram_total_gb >= T3_MIN_TOTAL_GB:
        return "T3", f"total RAM {ram_total_gb:g} GB >= {T3_MIN_TOTAL_GB:g} GB"
    if gpu_class == "apple_silicon" and ram_total_gb >= T3_APPLE_MIN_TOTAL_GB:
        return (
            "T3",
            f"Apple Silicon with {ram_total_gb:g} GB unified >= {T3_APPLE_MIN_TOTAL_GB:g} GB",
        )
    return "T2", f"standard: {ram_available_gb:g} GB available / {ram_total_gb:g} GB total"


def resolve_role_models(
    tier: str,
    models_available: list[str],
    ollama_reachable: bool,
) -> tuple[RoleModels, list[str]]:
    """Role→model map for a tier + degradation notes.

    ROLE_MODEL_<ROLE> env vars win over everything (spec override precedence).
    """
    notes: list[str] = []
    embedding = reranker = small = primary = coordinator = None

    if tier != "T0":
        embedding = DEFAULT_EMBEDDING_MODEL
        reranker = DEFAULT_RERANKER_MODEL
        small = DEFAULT_SMALL_MODEL
        if tier == "T2":
            primary = DEFAULT_PRIMARY_MODEL
        elif tier in ("T3", "T4"):
            primary = T3_PRIMARY_MODEL
        if tier == "T4":
            # v3.0 capability flag only — non-null coordinator means "enabled".
            coordinator = primary
            notes.append("coordinator capability enabled (T4)")

        # Explicit degradation: qwen3.5 not pulled yet but qwen2.5:7b is served.
        if (
            primary
            and ollama_reachable
            and models_available
            and not any(t.startswith(primary) for t in models_available)
            and any(t.startswith(FALLBACK_PRIMARY_MODEL) for t in models_available)
        ):
            notes.append(
                f"primary degraded to {FALLBACK_PRIMARY_MODEL}: {primary} not in "
                f"ollama tags (run install/pull-models.sh)"
            )
            primary = FALLBACK_PRIMARY_MODEL

    role_models = RoleModels(
        embedding=embedding,
        reranker=reranker,
        small=small,
        primary=primary,
        coordinator=coordinator,
    )

    # Env overrides win (ROLE_MODEL_EMBEDDING, ROLE_MODEL_PRIMARY, ...)
    overridden = {}
    for role in ROLES:
        env_value = os.getenv(f"ROLE_MODEL_{role.upper()}")
        if env_value:
            overridden[role] = env_value
    if overridden:
        role_models = role_models.model_copy(update=overridden)
        notes.append("env overrides: " + ", ".join(sorted(overridden)))

    return role_models, notes


# ── Resolver ───────────────────────────────────────────────────────────

class TierResolver:
    """Probes the machine, resolves the tier, caches with TTL, persists atomically."""

    def __init__(self, config: Config | None = None, ttl_seconds: float | None = None):
        self._config = config or Config.from_env()
        self._ttl_override = ttl_seconds
        self._lock = threading.RLock()
        self._cached: HardwareProfile | None = None
        self._cached_at: float = 0.0

    # ── Configuration helpers ─────────────────────────────────────

    @property
    def ttl_seconds(self) -> float:
        if self._ttl_override is not None:
            return self._ttl_override
        try:
            return float(os.getenv("MODEL_TIER_TTL", str(DEFAULT_TTL_SECONDS)))
        except ValueError:
            logger.warning("Invalid MODEL_TIER_TTL — using default %ss", DEFAULT_TTL_SECONDS)
            return DEFAULT_TTL_SECONDS

    def _root(self) -> Path:
        if self._config.server_dir:
            return Path(self._config.server_dir)
        return _project_root()

    def _system_dir(self) -> Path:
        data_dir = Path(self._config.data_dir) if self._config.data_dir else self._root() / "data"
        return data_dir / "system"

    # ── Probes (instance methods so tests can monkeypatch them) ───

    def _probe_hardware(self) -> dict:
        return probe_hardware()

    def _probe_backends(self) -> tuple[BackendMap, list[str]]:
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        llama_server_url = f"http://127.0.0.1:{os.getenv('LLAMA_SERVER_PORT', '8080')}"

        ollama_status, ollama_models = _check_ollama(ollama_url)
        llama_server_status = _check_llama_server(llama_server_url)
        llama_cpp_status, gguf_models = _check_llama_cpp_local(self._root())

        backends = BackendMap(
            ollama=ollama_status,
            llama_server=llama_server_status,
            llama_cpp_local=llama_cpp_status,
        )
        return backends, [*ollama_models, *gguf_models]

    # ── Core resolution ───────────────────────────────────────────

    def resolve(self, force: bool = False) -> HardwareProfile:
        """Resolve the profile, honoring the TTL cache unless forced."""
        with self._lock:
            if (
                not force
                and self._cached is not None
                and (time.monotonic() - self._cached_at) < self.ttl_seconds
            ):
                return self._cached

            old = self._cached
            profile = self._build_profile()
            self._cached = profile
            self._cached_at = time.monotonic()

            self._log_transition(old, profile)
            self._persist(profile, old)
            return profile

    def _build_profile(self) -> HardwareProfile:
        hw = self._probe_hardware()
        backends, models_available = self._probe_backends()
        any_llm = (
            backends.ollama.reachable
            or backends.llama_server.reachable
            or backends.llama_cpp_local.reachable
        )

        tier, reason = decide_tier(
            gpu_class=hw["gpu_class"],
            ram_total_gb=hw["ram_total_gb"],
            ram_available_gb=hw["ram_available_gb"],
            any_llm_backend=any_llm,
        )

        # MODEL_TIER override wins over resolution (auto = computed)
        override = os.getenv("MODEL_TIER", "auto").strip().lower()
        if override and override != "auto":
            forced = override.upper()
            if forced in VALID_TIERS:
                tier, reason = forced, f"forced by MODEL_TIER={override}"
            else:
                logger.warning("Invalid MODEL_TIER=%r — falling back to auto", override)

        role_models, notes = resolve_role_models(
            tier, models_available, backends.ollama.reachable
        )
        if notes:
            reason = f"{reason}; " + "; ".join(notes)

        return HardwareProfile(
            probed_at=_utcnow_iso(),
            hostname=hw["hostname"],
            os=hw["os"],
            arch=hw["arch"],
            cpu=hw["cpu"],
            logical_cores=hw["logical_cores"],
            ram_total_gb=hw["ram_total_gb"],
            ram_available_gb=hw["ram_available_gb"],
            gpu_class=hw["gpu_class"],
            backends=backends,
            models_available=models_available,
            tier=tier,
            tier_reason=reason,
            role_models=role_models,
        )

    # ── Triggers ──────────────────────────────────────────────────

    def force_refresh(self) -> HardwareProfile:
        """Fresh probe (health_check / model_tier_status / GET /api/model-tier)."""
        return self.resolve(force=True)

    def maybe_refresh(self) -> HardwareProfile | None:
        """Heartbeat piggyback: re-probe ONLY when the TTL cache expired.

        Never raises — heartbeats must stay cheap and unbreakable.
        """
        if (
            self._cached is not None
            and (time.monotonic() - self._cached_at) < self.ttl_seconds
        ):
            return None
        try:
            return self.resolve()
        except Exception as e:
            logger.warning("Periodic tier refresh failed: %s", e)
            return None

    def notify_backend_failure(self, backend: str) -> HardwareProfile:
        """Reactive hook: a backend connection failed → immediate re-probe."""
        logger.warning(
            "Backend failure reported for %r — invalidating tier cache and re-probing",
            backend,
        )
        return self.resolve(force=True)

    # ── Logging / persistence / instrumentation ───────────────────

    def _log_transition(self, old: HardwareProfile | None, new: HardwareProfile) -> None:
        if old is None:
            logger.info(
                "Model tier resolved: %s (%s) role_models=%s",
                new.tier,
                new.tier_reason,
                new.role_models.model_dump(exclude_none=True) if new.role_models else {},
            )
            return
        if old.tier != new.tier:
            logger.warning(
                "Tier transition %s → %s (%s)", old.tier, new.tier, new.tier_reason
            )
            self._emit_l0_event(
                f"model tier transition {old.tier} → {new.tier}",
                {"old_tier": old.tier, "new_tier": new.tier, "reason": new.tier_reason or ""},
            )

    @staticmethod
    def _profile_diff(old: dict | None, new: dict) -> dict:
        """Changed keys between two persisted profiles (probed_at excluded)."""
        if not old:
            return {}
        diff: dict = {}
        keys = set(old) | set(new)
        keys.discard("probed_at")
        for key in sorted(keys):
            if old.get(key) != new.get(key):
                diff[key] = {"old": old.get(key), "new": new.get(key)}
        return diff

    def _persist(self, profile: HardwareProfile, old: HardwareProfile | None) -> None:
        """Atomic write (tmp + os.replace) with the diff logged."""
        path = self._system_dir() / "hardware-profile.json"
        new_data = profile.to_persistable()

        old_data: dict | None = old.to_persistable() if old else None
        if old_data is None and path.exists():
            try:
                old_data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning("Previous hardware profile unreadable: %s", e)

        diff = self._profile_diff(old_data, new_data)
        if diff:
            logger.info("Hardware profile changed: %s", json.dumps(diff, default=str))

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / (path.name + ".tmp")
            tmp.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("Could not persist hardware profile to %s: %s", path, e)

    def _emit_l0_event(self, message: str, attributes: dict) -> None:
        """Append a system event to the L0 audit trail (RawEvent-shaped)."""
        jsonl = self._config.L0_events_jsonl
        if not jsonl:
            return
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": _utcnow_iso(),
            "type": "system",
            "source": "model_tier",
            "actor_id": "system",
            "session_id": "",
            "scope": "",
            "attributes": {"message": message, **attributes},
            "context": {},
        }
        try:
            path = Path(jsonl)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except OSError as e:
            logger.warning("Could not append L0 system event: %s", e)

    def record_outcome(self, task: str, model: str, ok: bool) -> None:
        """Instrumentation for learned-task-routing: task→model→outcome tuples."""
        line = {"ts": _utcnow_iso(), "task": task, "model": model, "ok": bool(ok)}
        path = self._system_dir() / "routing-outcomes.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
        except OSError as e:
            logger.warning("Could not record routing outcome: %s", e)

    # ── Consumers ─────────────────────────────────────────────────

    def preferred_llm_backend(self) -> str:
        """Backend for the LLM factory when LLM_BACKEND is unset.

        Prefers ollama when reachable, else llama_cpp; raises
        LLMUnavailableError at T0 so no caller degrades silently.
        """
        profile = self.resolve()
        backends = profile.backends
        if backends.ollama.reachable:
            return "ollama"
        if backends.llama_server.reachable or backends.llama_cpp_local.reachable:
            return "llama_cpp"
        from shared.llm.base import LLMUnavailableError  # late import — avoids cycles

        raise LLMUnavailableError(
            f"No LLM backend reachable (tier {profile.tier}): "
            f"ollama={backends.ollama.detail or 'down'}, "
            f"llama_server={backends.llama_server.detail or 'down'}, "
            f"llama_cpp_local={backends.llama_cpp_local.detail or 'down'}"
        )


# ── Module-level singleton API ─────────────────────────────────────────

_resolver: TierResolver | None = None
_resolver_lock = threading.Lock()


def get_resolver() -> TierResolver:
    global _resolver
    with _resolver_lock:
        if _resolver is None:
            _resolver = TierResolver()
        return _resolver


def resolve(force: bool = False) -> HardwareProfile:
    return get_resolver().resolve(force=force)


def force_refresh() -> HardwareProfile:
    return get_resolver().force_refresh()


def maybe_refresh() -> HardwareProfile | None:
    return get_resolver().maybe_refresh()


def notify_backend_failure(backend: str) -> HardwareProfile:
    return get_resolver().notify_backend_failure(backend)


def preferred_llm_backend() -> str:
    return get_resolver().preferred_llm_backend()


def record_outcome(task: str, model: str, ok: bool) -> None:
    get_resolver().record_outcome(task, model, ok)


def status() -> dict:
    """Fresh profile as a plain dict (MCP tool / sidecar endpoint payload)."""
    return force_refresh().to_persistable()
