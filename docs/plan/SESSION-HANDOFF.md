# Session handoff — 2026-07-12

> State snapshot for the next session. Read this + `IMPROVEMENT-PLAN.md` §4 before doing anything. Do NOT re-audit.

## Done today (committed locally, NOT pushed — push needs Rubén's OK)

1. **Team audit** (architect/backend/database/testing): 12 P0s found and mapped — see plan §2. Key: embedding truncation >200 chars, zero-vectors persisted, L2 false "saved", plugin `backpack-orchestrator.ts` missing from repo, version identity crisis, no CI.
2. **Plan v2** (`docs/plan/IMPROVEMENT-PLAN.md`): phases 0-6, OpenSpec operating model, quality gates §3.4, **adaptive model stack** §3.5-bis. ADR-0004 (Ollama + adaptive backends), ADR-0006 (2026 model matrix + embedding integrity policy). `openspec/` scaffolded (project.md, model-stack spec + JSON Schema, changes: ollama-backend, adaptive-model-tier).
3. **Implemented + green (209 passed, 6 skipped)**:
   - `shared/llm/ollama.py` (OllamaBackend, typed errors), tier-aware factory in `shared/llm/config.py`, `rank_by_relevance` top_k fallback fix.
   - `shared/model_tier.py`: HardwareProfile + TierResolver T0-T4, triggers startup/TTL-periodic/reactive (`notify_backend_failure`)/on-demand; MCP tool `model_tier_status`; `GET /api/model-tier`; atomic persistence `data/system/hardware-profile.json`; outcome instrumentation `data/system/routing-outcomes.jsonl` (future learned router dataset).
   - `_verify_stale` 3 bugs fixed (filter `any`, status logic, `set_payload` payload-only update, new `qdrant_client.set_payload`).
   - Configs aligned (`MODEL_TIER=auto`, `SMALL_LLM_MODEL=qwen3.5:2b`, full `.env.example`), `install/pull-models.sh` ready.
   - Verified on this machine: resolver → T2, Ollama reachable, primary explicitly degraded to `qwen2.5:7b` until pulls run.

## Immediate next steps (in order)

1. **Run `install/pull-models.sh`** (~4.6 GB: qwen3.5:4b, qwen3.5:2b, qwen3-embedding 0.6b) → re-run tier smoke: primary must flip to `qwen3.5:4b` with no config change.
2. **Phase 0 remainder**: fix `install/bootstrap.sh` (warn counter :26, error attribution :290, status-write on abort under `set -euo pipefail`); README truth pass (real tree, real install, no launchd claim, no `plugins/` reference, test count 209); delete `VAULT_PATCHES.json` + `etc/`; fix `.gitignore:66`.
3. **Phase 1** (plan §4): CI + gates, CHANGELOG, CONTRIBUTING, ADR-0001/0002/0003/0005, **recover plugin** `backpack-orchestrator.ts` (search OpenCode config dirs; fallback: rewrite from `docs/architecture/SPEC-backpack-v1.2.md`) into `adapters/opencode/` with Vitest.
4. **Phase 2** (v2.2.0) changes per plan table — parallelizable: `fix-embedding-truncation` ∥ `vault-integrity` ∥ `honest-l2-status`; then `no-zero-vectors`, `qdrant-write-integrity`, `logging-root-fix`, `sqlite-migrations`, `model-stack-2026`, `reranker-real`, `resilience-suite`.

## Late additions (2026-07-12, after first commit batch — all committed)

- **Binding verification protocol** `openspec/AGENTS.md`: nothing fake/demo/mock, dual validation (2 independent sources) for every assumption, strict TDD with verbatim red→green evidence in `openspec/changes/<id>/evidence/I<NN>.md`, numbered iterations mapped 1:1 to tasks.md. Referenced from CLAUDE.md; LOOP-PROMPT updated to v2.
- **ADR-0007**: hexagonal/SOLID/DRY enterprise architecture; strangler migration to `domain/ports/adapters/app/runtime` starting Phase 3 (`composition-root`, `hexagonal-shared-split`); boy-scout rule binding.
- **ADR-0008 + Phase 3-bis**: auto-started control plane — Web SPA at `:8890/ui` (launchd KeepAlive) + Textual TUI (`amem`), config/profiles/metrics via validated `/v1` API only; ROADMAP "Not doing: web dashboard" overridden.

## Open items / decisions pending

- **Push to origin**: awaiting Rubén's approval (commits are local).
- `tests/app` silent-skip → becomes failure under `CI=1` (Phase 1.4).
- `learned-task-routing`: deferred research; instrumentation already collecting data.
- Known cosmetic: `maybe_refresh` can block the loop a few seconds once per TTL; `ram_available_gb` diff logs INFO each re-probe.
