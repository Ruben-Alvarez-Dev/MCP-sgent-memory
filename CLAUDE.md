# CLAUDE.md — MCP-agent-memory

Persistent multi-layer memory for AI coding agents: Python MCP server (53 tools, 7 `Lx_*` modules in `src/`), HTTP sidecar :8890, Qdrant (dim 1024) + SQLite FTS5 + bilingual ES/EN vault. Full context: `docs/plan/IMPROVEMENT-PLAN.md` (master plan v2), `docs/plan/SESSION-HANDOFF.md` (latest state), `openspec/` (specs + change proposals), `docs/adr/`.

## Hard rules (Rubén's norms — always apply)

- **VERIFICATION PROTOCOL (binding, overrides everything): `openspec/AGENTS.md`** — nothing mockup/demo/fake; no claim without executable proof; every assumption dual-validated against 2 independent sources; TDD (red→green evidence captured verbatim); work only as numbered iterations `I<NN>` inside approved openspec changes, each with committed evidence file. Unverifiable ⇒ report as UNVERIFIED, never as working.
- **Spec-driven**: no code without an approved `openspec/changes/<id>/` proposal (bugfixes: lightweight proposal). Specs/docs in English; **reply to Rubén in Spanish**.
- Conventional Commits, English, granular. **Never push without Rubén's explicit approval.** Never commit with red tests.
- No mocks/fakes outside `tests/`. Typed exceptions; never `except: pass`. Loggers must use the `agent-memory.*` namespace (others don't reach server.log).
- No new dependencies in `pyproject.toml` without an ADR. Surgical minimal diffs; don't reformat unrelated code.
- Model/backend selection is NEVER hardcoded: it flows through `shared/model_tier.py` (tiers T0-T4, adaptive per machine — see ADR-0004/0006 and `openspec/specs/model-stack/`).
- **Architecture (ADR-0007)**: hexagonal ports & adapters, SOLID, DRY, enterprise normalization. All I/O behind a port; no duplication (extract, don't copy); strangler migration — every module you touch moves to the target layout (`domain/ports/adapters/app/runtime`); no cross-imports between Lx modules; abstraction at every I/O/policy boundary, none on single-consumer internals.

## This machine

Hackintosh — Ryzen 5 5600G, 16 GB RAM, RX 570: **CPU-only inference**; llama.cpp Metal unreliable here; Ollama at `127.0.0.1:11434` is the LLM/embedding backend (tier resolver handles it). `deps/vendor/` wheels are arm64 (other machine). Don't attempt GPU builds here.

## Commands

- Tests: `PYTHONPATH=src .venv/bin/python -m pytest tests/core -q` (no services needed; `tests/app` needs Qdrant+embeddings and skips otherwise)
- Lint: `.venv/bin/ruff check src tests`
- New-model pulls (~4.6 GB, explicit): `install/pull-models.sh`
- Tier smoke: `PYTHONPATH=src MEMORY_SERVER_DIR=$PWD .venv/bin/python -c "from shared.model_tier import get_resolver; print(get_resolver().force_refresh().tier)"`

## Orchestration & token discipline

- Orchestrate from the main context; **delegate all exploration and implementation to subagents** (`jart-dev-team:dev-software-architect / dev-backend-specialist / dev-database-specialist / dev-frontend-specialist / dev-testing-specialist`). Launch independent work in parallel (one message, multiple Task calls).
- Trust the plan and the 2026-07-12 audits — **do not re-audit the repo**. Read files with offset/limit; batch tool calls; don't re-read files after editing; subagent reports capped at ~300 words.
- Per change: proposal → implement → targeted pytest → full `tests/core` once → ruff → granular commit(s) → tick `tasks.md` → archive change into `openspec/specs/`.
- Ask Rubén (in Spanish) only at: phase boundaries, pushes, failures after 2 fix attempts, scope ambiguity.
