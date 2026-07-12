# Spec — model-stack (current truth after changes ollama-backend + adaptive-model-tier)

Status: current | Last-verified: 2026-07-12

> Normative source: ADR-0004, ADR-0006. Schema: `hardware-profile.schema.json` (v1.0).

## Capability: adaptive model resolution

The system SHALL resolve which models serve each role (embedding, reranker, small, primary, coordinator) at runtime from a machine capability probe — never from install-time assumptions.

### Tiers

| Tier | Condition (defaults) | Roles enabled |
|------|----------------------|---------------|
| T0 degraded | no LLM backend reachable | embeddings only if reachable; heuristic summaries; loud logging; health `degraded` |
| T1 edge | < 6 GB available RAM or only micro feasible | embedding 0.6B + reranker 0.6B + small ≤2B |
| T2 standard | ≥ 6 GB available (this Hackintosh) | + primary 4B (Qwen3.5-4B) |
| T3 workstation | ≥ 32 GB total or Apple Silicon ≥ 24 GB unified | primary 9B class |
| T4 coordinator | ≥ 64 GB + accelerator | + hive coordinator (long-context) — the ONLY way v3.0 coordinator activates |

Thresholds are constants in `shared/model_tier.py`, overridable via `MODEL_TIER` / `ROLE_MODEL_*` env.

### Verification triggers (hook semantics)

1. **Startup** — `_ensure_initialized` resolves before first tool call.
2. **Periodic** — heartbeat re-probes when cache older than `MODEL_TIER_TTL` (default 900 s).
3. **Reactive** — any backend connection failure calls `notify_backend_failure()` → immediate re-probe, possible downgrade, logged + L0 system event.
4. **On demand** — `health_check` and MCP tool `model_tier_status` / `GET /api/model-tier` force a fresh probe.

Tier transitions MUST be logged at WARNING with old→new tier and reason, and MUST be visible in `health_check` output.

### Default role→model matrix (T2)

embedding: `qwen3-embedding:0.6b` (dim 1024) · reranker: `qwen3-reranker:0.6b` (until `reranker-real` lands, prompt-ranking remains flagged deprecated) · small: `qwen3.5:2b` · primary: `qwen3.5:4b` · coordinator: null.

Licenses: defaults MUST be Apache-2.0/MIT (ADR-0006 §5).
