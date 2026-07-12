# Change: adaptive-model-tier

- **Status**: approved (Rubén, 2026-07-12) — implementation started
- **Owner**: backend · **Release**: v2.2.0 (pulled forward with Phase 0)

## Why

The same repo runs on machines with radically different capabilities (Hackintosh x86 16 GB CPU-only today; Apple Silicon studio Mac; future ≥64 GB boxes). Model choice is currently hardcoded in env files, half-migrated, and inconsistent with the code — the primary LLM is silently dead. Features like the v3.0 hive coordinator (1M context) must **auto-enable only where the hardware supports them** (Rubén's requirement), verified regularly AND reactively to changes (hook semantics), not assumed at install time.

## What

1. `shared/model_tier.py`: `HardwareProfile` probe (stdlib only) + `TierResolver` mapping profile → tier **T0 degraded / T1 edge / T2 standard / T3 workstation / T4 coordinator** → role→model map (embedding, reranker, small, primary, coordinator).
2. Triggers: startup · periodic (heartbeat piggyback, `MODEL_TIER_TTL`, default 900 s) · **reactive** (backend connect failure → immediate re-probe + possible downgrade) · `health_check` always re-probes · exposed as MCP tool `model_tier_status` + sidecar `GET /api/model-tier`.
3. Persistence: `data/system/hardware-profile.json` (atomic write); profile diffs logged + ingested as L0 system events.
4. Overrides: `MODEL_TIER=auto|t0..t4`, `ROLE_MODEL_<ROLE>` env vars win over resolution.
5. Instrumentation for `learned-task-routing`: log task→model→outcome tuples from day one.

## Impact

- Touches: `shared/model_tier.py` (new), `shared/llm/config.py` (factory consults resolver when `LLM_BACKEND` unset), `shared/api_server.py` (endpoint), unified server `_ensure_initialized` + `health_check`.
- Spec deltas: `openspec/specs/model-stack/` (matrix + `hardware-profile.schema.json`).
- Non-goals: no automatic model downloads (pull scripts are explicit); no coordinator implementation (v3.0) — only the capability flag.

## Acceptance

- On this Hackintosh resolves T2 with Ollama backend; with Ollama stopped → reactive downgrade to T0 within one failed call, loudly logged, health shows `degraded`.
- Unit tests: profile parsing, tier boundaries (RAM thresholds), override precedence, downgrade path — no external services required.
