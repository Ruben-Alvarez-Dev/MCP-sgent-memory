# MCP-agent-memory — Improvement & Delivery Plan

> **Date**: 2026-07-12 · **Status**: APPROVED v2 — development started 2026-07-12
> **v2 amendments**: real hardware profile (Hackintosh, CPU-only), 2026 model stack, **adaptive model-tier system** (Rubén's requirement: capability detection per machine, periodic + reactive/hook re-checks, hive coordinator auto-enabled only where supported), decision 0.1 flipped to OllamaBackend.
> **Method**: 100% spec-driven (OpenSpec + open standards). No code lands without an approved spec/change proposal.
> **Produced by**: dev-team orchestration — architect, backend, database, testing audits (read-only, this working tree at `c16c2c0` + 5 uncommitted files).

---

## 1. Executive Summary

The project has a strong design narrative (README, ROADMAP, research docs) but the repo no longer tells the truth about itself, and four independent audits found data-corrupting P0 defects that the ROADMAP does not know about. The plan below (a) stabilizes the repo and this machine's install, (b) installs a spec-driven operating model with document/dev/production standards, then (c) delivers the pending roadmap (v1.5.1 → hive) as OpenSpec change proposals with quality gates.

**Headline findings** (full detail in §2):

1. `backpack-orchestrator.ts` — the component that makes the system "automatic" — **is not in the repository**. README installation instructions are broken.
2. **Silent data corruption in the embedding pipeline**: every text >200 chars is embedded by its first 200 chars only (`shared/embedding.py` `get_embedding` cache-key bug), the persistent cache is keyed without model/dimension, and failures persist zero-vectors that pass validation but are invisible to search.
3. **L2_conversations "silent failure" is real and compound**: Qdrant errors are swallowed and `status="saved"` is returned anyway; module loggers never reach `server.log`; Qdrant upserts don't check HTTP status; `save_thread` is delete-and-replace.
4. **Version identity crisis**: git tags reach v2.0.0, `pyproject.toml` says 2.1.0, README calls "v2.0" current, ROADMAP calls "v2.0" future (hive). No CHANGELOG, no rule.
5. **No CI, no gates, no plugin tests**: 186 tests exist (README says 164) but nothing runs them automatically; `tests/app/` skips silently when services are down; the HTTP sidecar and 6/7 Lx modules have no handler tests.
6. Local install on this machine is half-done (Qdrant ✅, embedding/LLM ❌, `bootstrap.sh` has 3 diagnostic bugs) and the 5 uncommitted files encode an unfinished Ollama migration that currently **breaks LLM synthesis at runtime** (`LLM_BACKEND=ollama` is rejected by `shared/llm/config.py`).

**Release strategy**: one SemVer line (2.x), ROADMAP items renumbered as releases — Phase 2 → **v2.2.0** (data integrity), Phase 3 → **v2.3.0** (v1.5.1 full conversation serialization), Phase 4 → **v2.4.0** (v1.6.1 timeline backbone), Phase 5 → **v2.5.0** (v1.8 embedding upgrade), Phase 6 → **v3.0.0** (agent hive, absorbing v1.6 KV-cache research).

---

## 2. Consolidated Audit Findings

Sourced from four specialist audits (architect, backend, database, testing). References are `path:line` in this working tree.

### 2.1 P0 — data loss, corruption, or broken truth

| # | Finding | Evidence | Owner |
|---|---------|----------|-------|
| P0-1 | Plugin `backpack-orchestrator.ts` absent from repo; `plugins/`, `adapters/` don't exist; README:330 install step is broken | repo tree | architect |
| P0-2 | Embedding truncation: `cache_key = text[:200]` is what actually gets embedded; full-text path unreachable; persistent cache poisoned under full-text hash | `shared/embedding.py:524-533` | database |
| P0-3 | Embedding cache keyed by `sha256(text)` without model/dimension → model swap serves stale 384d vectors; no eviction | `shared/embedding_cache.py` | database |
| P0-4 | `safe_embed` returns `[0.0]*1024` on failure; zero-vectors are persisted as real memories (unsearchable, corrupt) | `shared/embedding.py:600-616` | database |
| P0-5 | L2 false success: Qdrant embed+upsert wrapped in `except → logger.warning`, returns `status="saved"` regardless; SQLite saves, vector doesn't | `L2_conversations/server/main.py:82-91` | backend |
| P0-6 | Qdrant writes unverified: `upsert`/`upsert_batch`/`ensure_collection` never `raise_for_status()`; dimension of existing collections never validated | `shared/qdrant_client.py:198-232` | database |
| P0-7 | Logging tree broken: `setup_logging` configures `"agent-memory"` tree only; L2/shared use `getLogger(__name__)` → critical warnings never reach `server.log` | `shared/logging_config.py:18` | backend |
| P0-8 | Uncommitted Ollama migration incoherent: `config/mcp.json` sets `LLM_BACKEND=ollama` but `shared/llm/config.py:176-185` only accepts `llama_cpp` → ValueError; no `OllamaBackend` exists; all LLM synthesis silently degraded | working tree | backend |
| P0-9 | `_verify_stale` (uncommitted): status unconditionally overwritten to "verified" (:190-191), upsert with `vector=None` (:202-203), invalid Qdrant filter syntax (:127) — bugs mutually cancel, feature inert | `L0_to_L4_consolidation/server/main.py` | backend |
| P0-10 | Vault re-serialization loop: `is_serialized()` regex uses `d` instead of `\d` → never matches → infinite renames, inflated counter, duplicate EN copies | `bin/vault_processor.py:38` | database |
| P0-11 | Bootstrap diagnostics lie: `warn()` never increments WARNINGS; wrong error attribution at :290; `set -euo pipefail` can abort without writing status. This machine: EMB=false, ERRORS=1, no `engine/bin/llama-server`, no models | `install/bootstrap.sh:17,26,290` | architect |
| P0-12 | No CI, no gates, no automated test run; `tests/app/` skips silently without services (deceptive green) | repo tree | testing |

### 2.2 P1 — architecture & reliability debt

- Four overlapping entrypoints (`unified/server/main.py`, `backpack.py`, `main_http.py`, `gateway.py` — the latter needs undeclared `aiohttp`, dead code). Module loading duplicated 3×. (backend/architect)
- Shared `httpx.AsyncClient` crosses event loops (MCP loop vs sidecar thread loop) → intermittent RuntimeErrors swallowed by the same excepts. (backend)
- HTTP sidecar: no input validation (`fn(**body)` → TypeError → generic 500), no `/v1` versioning, no written contract; FastAPI migration trivial (typed signatures + Pydantic results; starlette/uvicorn already vendored). (backend)
- 95 `except Exception` across 27 files, 19 `except: pass`; `status()` tools return "RUNNING" unconditionally. (backend)
- Three competing vault paths (`data/vault` vs `<repo>/vault` vs `data/Lx-persistent`); `counter.json` read-modify-write without lock in two competing implementations; "EN translation" is actually `shutil.copy2` of Spanish content; ES/EN writes non-transactional. (database)
- SQLite: no `PRAGMA user_version`, ad-hoc probe migration; `save_thread` delete-and-replace invalidates message ids; `MemoryItem.ttl` never read. (database)
- Lineage broken: `source_event_ids` only populated in `ingest_event`; omitted in `memorize` and in all L1→L4 consolidation. `MemoryType.ENTITY/RELATION` and `MemoryScope` have zero logic (confirmed). (database)
- Test coverage holes: HTTP sidecar 0 tests, 6/7 Lx module handlers 0 tests, embedding fallback 0 tests, Qdrant-down resilience 0 tests. (testing)
- README↔reality drift: `etc/` is a zombie dir (config really lives in `config/`), no launchd `.plist` exists anywhere (README claims launchd services), vault tree doesn't match documented ES/EN layout, `deps/vendor/` (33 wheels) undocumented and unused by bootstrap. (architect)

### 2.3 P2 — hygiene

`VAULT_PATCHES.json` = already-applied find/replace pseudo-migrations on source code (anti-pattern, delete). `.gitignore:66` literal `$HOME/`. `config/.env.example` documents 3 of ~15 real keys. README test count stale (164 vs 186). `ARCHITECTURE.md` header stuck at v1.2. Bench scripts not reproducible (hand-started stack, print-based). Logging unstructured, no correlation IDs.

---

## 3. Target Operating Model — 100% Spec-Driven

### 3.1 OpenSpec as the workflow backbone

Adopt [OpenSpec](https://github.com/Fission-AI/OpenSpec) conventions. New top-level directory:

```
openspec/
├── AGENTS.md          # how AI assistants must work in this repo (gates, norms, personas)
├── project.md         # tech stack, architecture, conventions, domain glossary
├── specs/             # THE TRUTH — current deployed capabilities, one folder per capability
│   ├── l0-capture/ … l5-routing/, lx-reasoning/
│   ├── http-sidecar/  # OpenAPI-backed
│   ├── embedding-pipeline/
│   ├── vault/
│   └── plugin-orchestrator/
└── changes/           # PROPOSALS — active work; archived into specs/ on completion
    └── <change-id>/   # proposal.md (why/what), design.md (how), tasks.md (checklist), spec deltas
```

Rules: (1) `specs/` is read-only during feature work — it changes only by archiving an approved change. (2) Every phase item below becomes one or more `changes/<id>/`. (3) A change may not merge until its tasks are checked, its spec delta is written, and quality gates pass. (4) Bugfixes above P2 also go through a (lightweight) change proposal — that is what "100%" means.

### 3.2 Open standards matrix (normative)

| Concern | Standard | Applied to |
|---------|----------|------------|
| API contract | **OpenAPI 3.1** | HTTP sidecar (`/v1/*`), generated from FastAPI, committed at `openspec/specs/http-sidecar/openapi.yaml` |
| Data formats | **JSON Schema 2020-12** | `RawEvent` (L0 JSONL), `MemoryItem` Qdrant payload, `dream/state.json`, `conversation record` (Phase 3), `config/mcp.json` env block — each with `schema_version` field |
| Decisions | **MADR 4.0** | `docs/adr/NNNN-*.md`; ADRs are immutable, superseded not edited |
| Commits | **Conventional Commits 1.0** | enforced by commitlint config + PR title check; English, granular (existing team norm) |
| Versioning | **SemVer 2.0** | single 2.x line; tag every release; `pyproject.toml` is the single source of version |
| Changelog | **Keep a Changelog 1.1** | root `CHANGELOG.md`, reconstructed from tags v1.0.0→v2.1.0 once, then maintained per release |
| Style/lint | **ruff** (lint+format), **mypy --strict** on `src/shared/models`, gradual elsewhere | pre-commit + CI |
| Tests | **pytest + pytest-cov**; Vitest for the TS plugin | gates in §3.4 |
| Editor/format | **EditorConfig** | root `.editorconfig` |
| Docs language | **English** (repo), Spanish remains user-facing in the vault ES tree | all specs/ADRs/README |

### 3.3 Documentation normalization

- `README.md` must describe only what exists; regenerate the structure section from the real tree; fix install instructions; test count auto-generated.
- `docs/architecture/` = current-state explanations only; anything aspirational moves to `openspec/changes/`; `docs/ROADMAP.md` becomes a thin index pointing at change proposals + release targets.
- `docs/adr/` created with ADR-0001..0006 (see Phase 1).
- `docs/archive/` untouched (history). `VAULT_PATCHES.json` and `etc/` deleted (ADR-recorded).
- Every doc gets a header: `Status: current | proposal | archived`, `Last-verified: <date>`.

### 3.4 Development standards & quality gates

Gates (from testing audit, adopted as-is):

1. **CI core job** (push/PR): `pip install -e ".[dev]"` + `PYTHONPATH=src pytest tests/core -q` — no services required, mandatory.
2. **CI integration job**: Qdrant service container + lightweight embedding stub; `CI=1` turns `tests/app/` silent skips into **failures**.
3. **Lint gate**: `ruff check` + `ruff format --check` (+ mypy on typed cores).
4. **Coverage gate**: `--cov-fail-under=60` initial, ratchet-only policy.
5. **Pre-push hook** (local, <30 s): `pytest tests/core -q && ruff check` via pre-commit.
6. **Sidecar contract suite**: `tests/core/test_api_server.py` with ASGI TestClient covering every `/v1` endpoint against the committed OpenAPI.
7. **Resilience suite**: Qdrant down → typed error propagated (no false "saved"); embedding down → write rejected or flagged `needs_reembedding`, never zero-vector.

Workflow: trunk-based, short-lived branches named `change/<openspec-id>`; PR requires green CI + linked change proposal; granular English commits; push per milestone (team norm).

### 3.5-bis Adaptive model stack & hardware tiers (v2)

**Hardware reality**: the current dev box is a Hackintosh — Ryzen 5 5600G (6c/12t, AVX2), 16 GB RAM, RX 570. llama.cpp Metal is unreliable on Polaris; Ollama on macOS x86 is CPU-only. All local inference is CPU. `deps/vendor/` arm64 wheels are useless here (targeted at the Apple Silicon machine). Ollama already serves `bge-m3` + `qwen2.5:7b` at :11434.

**Model stack (2026 refresh)** — per role, replacing the 2024-era stack:

| Role | Code touchpoint | Model (primary choice) | Size (q4/q8) | Notes |
|------|----------------|------------------------|--------------|-------|
| Embeddings | `shared/embedding.py`, all layers + queries | **Qwen3-Embedding-0.6B** (GGUF official) | ~0.6 GB | dim 1024 == BGE-M3 → no Qdrant migration; 32k ctx; corpus is empty → zero re-embedding cost. Watch: `tencent/R3-embedding-0.6b` (agent-skill retrieval finetune, 2026-07-08) |
| Reranker | replaces `rank_by_relevance` prompt hack | **Qwen3-Reranker-0.6B** (or bge-reranker-v2-m3) | ~0.6 GB | real cross-encoder; alt: `naver/xprovence-reranker-bgem3-v2` adds sentence pruning for the 2000-token injection budget; `KaLM-Reranker-V1-Small` GGUF (2026-07-06) llama.cpp-ready |
| Primary LLM | `_summarize` L0→L4, dream, narratives, vault ES↔EN translation | **Qwen3.5-4B** (2026-02, Apache-2.0, GGUF) | ~2.6 GB | beats qwen2.5-7B at half the RAM, ~2× CPU speed; multimodal (future screenshot ingestion) |
| Micro LLM | `_verify_stale` (v1.4), entity extraction (v1.6.1), structured JSON via grammar | **Qwen3.5-2B** (config default already points here) | ~1.4 GB | alt: MiniCPM5-1B (2026-05, tool-calling, long ctx) |
| Intent classifier | `classify_intent` L5 | **keep deterministic heuristic** | 0 | correct design; learned routing = research change (see below) |
| Hive coordinator | v3.0 only | long-context Qwen3.5 class | — | **enabled exclusively by tier resolver on capable machines** |

Total resident: ~4.1 GB (vs 5.9 GB current) with quality gains across every role.

**Adaptive model-tier resolver** (new subsystem, Rubén's explicit requirement): `shared/model_tier.py`.

- `HardwareProfile` (pydantic, stdlib probes only): os, arch, cpu, cores, ram_total/available, GPU class (apple_silicon | discrete | none), reachable backends (ollama, llama_server, llama_cpp binary+model), available models.
- Tier policy: **T0 degraded** (no LLM → heuristics, loudly logged) · **T1 edge** (embed+rerank+micro) · **T2 standard** (this box: + primary 4B) · **T3 workstation** (≥32 GB or Apple Silicon ≥24 GB: primary 9B) · **T4 coordinator** (≥64 GB + accelerator: hive coordinator flag ON — this is how v3.0 "runs or not" adaptively per machine).
- Role→model map resolved from tier; overridable via `MODEL_TIER` and `ROLE_MODEL_*` env vars.
- **Triggers (hook semantics)**: (a) startup (`_ensure_initialized`); (b) periodic — piggybacked on heartbeat with TTL (`MODEL_TIER_TTL`, default 15 min); (c) **reactive** — any backend connect failure forces immediate re-probe and possible downgrade; `health_check` always re-probes; (d) surfaced as MCP tool + `/api/model-tier`; tier changes are logged and ingested as L0 system events.
- Last profile persisted atomically at `data/system/hardware-profile.json`; diffs against previous profile are reported.
- JSON Schema: `openspec/specs/model-stack/hardware-profile.schema.json`.

**Learned task routing (research change, deferred)**: `SupraLabs/Supra-Router-51M` (2026-07-05, 51.8M, llama arch, MIT dataset) proves tiny CPU routers (<30 ms) can dispatch prompts by difficulty across model tiers. As-is it's not adoptable (English-only, trained on <1K rows). Adopted strategy: the tier resolver **instruments task→model→outcome from day one**, building the labeled dataset to later finetune a ~50M bilingual router for (a) micro-vs-primary escalation and (b) plugin-side "does this prompt need memory?" pre-classification. Tracked as change `learned-task-routing`.

### 3.5 Production standards

- **One daemon**: `backpack.py` becomes the single owner of `:8890` (shared composition root with the stdio entrypoint; `main_http.py`/`gateway.py` deleted or absorbed — ADR-0005).
- **launchd for real**: committed `.plist` templates under `install/launchd/` for backpack daemon, Qdrant watchdog, vault processor (replacing nohup/FIFO scripts), installed by `app-install.sh`.
- **Health contract**: `/v1/health` returns per-subsystem status (qdrant, embedding backend+model+dim, llm, vault, disk) with `degraded: true` semantics; `status()` tools must report reality, not "RUNNING".
- **Structured logging**: JSON lines to `~/.memory/server.log`, root-logger fix, correlation id per request/tool call.
- **Release process**: tag → CHANGELOG entry → GitHub release; install scripts must exit non-zero on real failure and write truthful `.bootstrap-status`.

---

## 4. Phased Plan

Each phase = a set of OpenSpec changes. **Nothing is implemented without your approval of the corresponding proposal.** Owners: A=architect, B=backend, D=database, T=testing.

### Phase 0 — Triage & local recovery (no feature work) · ~1 short session

Goal: honest repo, working install on this machine, clean tree. (Pre-OpenSpec: these are the only changes allowed to land spec-less, recorded retroactively in ADR-0001.)

| Item | Detail | Owner |
|------|--------|-------|
| 0.1 | **DECIDED (v2): implement `OllamaBackend`** — Ollama is already serving on this box and llama.cpp Metal is unreliable on this GPU; `llama_cpp` remains as fallback backend on machines where it fits (tier resolver decides) | A+B |
| 0.2 | Fix `_verify_stale` bugs before any commit of that file (filter syntax, status overwrite, `vector=None` → use `set_payload`) | B |
| 0.3 | Commit triage of the 5 modified files: `L3_facts` (clean, commit), `L5_routing` (add fallback consistency first), rest per 0.1/0.2 — granular commits | B |
| 0.4 | Fix `bootstrap.sh` (warn counter, error attribution, status-write on abort); re-run bootstrap → embedding server up, `health_check` green | A |
| 0.5 | Delete `VAULT_PATCHES.json` + `etc/`; fix `.gitignore:66` | A |
| 0.6 | README truth pass: real tree, real install, remove launchd claim until Phase 1 delivers it | A |

Exit criteria: clean `git status`; `health_check` all-green on this machine; README executable end-to-end.

### Phase 1 — Governance scaffolding (spec-driven from here on) · ~1-2 sessions

| Item | Detail | Owner |
|------|--------|-------|
| 1.1 | `openspec/` init: `project.md`, `AGENTS.md` (encodes team norms: no fakes outside tests, SOLID+hexagonal, approval-gated surgical changes, spec-before-code), baseline `specs/` written from current reality (the audits are the source material) | A |
| 1.2 | ADR-0001 current-state & triage record · ADR-0002 versioning (single 2.x SemVer line; hive renumbered v3.0) · ADR-0003 OpenSpec adoption · ADR-0005 single daemon entrypoint · (done 2026-07-12: ADR-0004 backends, ADR-0006 model policy, **ADR-0007 hexagonal/SOLID/DRY enterprise architecture** — includes import-linter contract in CI) | A |
| 1.3 | Root `CHANGELOG.md` (reconstructed), `CONTRIBUTING.md`, `.editorconfig`, pre-commit config, commitlint | A |
| 1.4 | CI: GitHub Actions with gates 1-5 (§3.4) | T |
| 1.5 | **Recover the plugin**: locate `backpack-orchestrator.ts` (OpenCode config dir on the studio Mac) → commit under `adapters/opencode/` with `package.json` + Vitest smoke tests; if unrecoverable, open change to rewrite from SPEC-backpack-v1.2.md | A+T |
| 1.6 | Publish JSON Schemas (RawEvent, MemoryItem payload, state.json) + `schema_version` fields | D |

Exit criteria: CI enforced on main; `openspec/specs/` baseline merged; plugin versioned in-repo.

### Phase 2 — Data integrity release → **v2.2.0** · ~2-3 sessions

The P0 bugfix batch, one OpenSpec change each (small, testable, reviewed):

| Change id | Content | Owner |
|-----------|---------|-------|
| `fix-embedding-truncation` | full-text embedding, cache key = sha256(text)+model+dim, cache invalidation + eviction, one-shot poisoned-cache purge script | D |
| `no-zero-vectors` | `safe_embed` → typed failure; callers reject or mark `needs_reembedding`; startup embed-probe verifying model+dimension logged | D |
| `qdrant-write-integrity` | `raise_for_status` on all writes, collection-dimension validation at startup, per-loop httpx clients | D+B |
| `honest-l2-status` | `SaveConversationResult` gains `degraded`/`qdrant_error`; `status="saved_sqlite_only"` semantics; sidecar propagates | B |
| `logging-root-fix` | root logger config or `agent-memory.*` renaming; structured JSON lines | B |
| `sqlite-migrations` | `PRAGMA user_version` + versioned migrations; stop delete-and-replace in `save_thread` (upsert by stable message key) | D |
| `vault-integrity` | regex fix, single VAULT_PATH, atomic+locked counter, transactional ES/EN pair or explicit copy semantics | D |
| `ollama-backend` | real `OllamaBackend` + config validation (**pulled forward: implemented 2026-07-12 with Phase 0**) | B |
| `adaptive-model-tier` | hardware profiler + tier resolver (T0-T4) + startup/periodic/reactive triggers + `/api/model-tier` (**pulled forward: implemented 2026-07-12**) | B |
| `model-stack-2026` | swap embeddings to Qwen3-Embedding-0.6B, primary to Qwen3.5-4B, micro to Qwen3.5-2B; pull scripts; acceptance benchmark vs old stack | D |
| `reranker-real` | replace `rank_by_relevance` prompt hack with cross-encoder (Qwen3-Reranker-0.6B / bge-reranker-v2-m3; evaluate xprovence pruning) | D |
| `learned-task-routing` | RESEARCH (deferred): instrument task→model→outcome now; finetune ~50M bilingual router later (Supra-Router pattern) | A |
| `resilience-suite` | gates 6-7 test suites (sidecar contract + failure injection) | T |

Exit criteria: all P0s closed with regression tests; coverage gate ≥60%; tag v2.2.0 + changelog.

### Phase 3 — Full conversation serialization (ROADMAP v1.5.1) → **v2.3.0** · ~2-3 sessions

Opens with the ADR-0007 structural changes: `composition-root` (single entrypoint/wiring, removes `main_http.py`/`gateway.py`) and `hexagonal-shared-split` (`shared/` → `domain/ports/adapters/app/runtime`, import shims, strangler + boy-scout rule thereafter). Then spec-first: `conversation-record` JSON Schema (timestamp, role, agent, tool+output, user, machine, environment, full content, summary — never truncated, no TTL). Then: FastAPI migration of the sidecar (`/v1`, validation, generated OpenAPI) as an `adapters/http_sidecar` implementation, full-thread capture path plugin→sidecar→SQLite (source of truth)→Qdrant (index, degradable), read-back API (filter by date/project/agent/tool), backfill from `raw_events.jsonl` where possible. Depends on Phase 2 (honest status, migrations). Owners: A (architecture changes), B (API), D (storage), T (contract tests).

### Phase 3-bis — Control plane: auto-started Web + TUI (ADR-0008) → **v2.3.5** · ~2-3 sessions

Change `control-plane-ui` (proposal committed): `ConfigService` + `MetricsCollector` ports, `/v1/config|profiles|metrics(+SSE)|threads` endpoints, Web SPA (Vite+Tailwind) served by the daemon at `:8890/ui`, TUI (Textual, `amem`), launchd `KeepAlive` auto-start, degraded read-only mode at T0. All parameters/configs/profiles managed through one validated, audited path; metrics/charts over real counters only. Depends on Phase 3 FastAPI `/v1`. Owners: F (SPA), B (API), T (Playwright + Textual pilot E2E), A (review).

### Phase 4 — Timeline backbone (ROADMAP v1.6.1) → **v2.4.0** · ~3 sessions

Spec-first: entity/relation model (activating `MemoryType.ENTITY/RELATION` with real logic or removing them — decided in the proposal), lineage repair (`source_event_ids` populated across memorize + all consolidation), temporal ordering API, entity lifecycle (birth/evolution/death), graph traversal endpoints, Engram-Go `mem_timeline` bridge decision (integrate or absorb). `MemoryScope` gets enforced semantics or is cut. Owners: D (model+graph), B (API), A (design ADRs).

### Phase 5 — Embedding pipeline upgrade (ROADMAP v1.8) → **v2.5.0** · ~1 session

Remaining after Phase 2: reference-vector health check (cosine >0.99 vs known vector), explicit fallback chain with loud logging (`llama_server → http → fail`), alternative backend support, embedding benchmark in CI (informational). Owner: D.

### Phase 6 — Agent hive (ROADMAP v2.0 → renumbered **v3.0.0**) + KV-cache research (v1.6)

Design-only until earlier phases ship: ADR series for coordinator architecture, agent-scoped L1 + shared L3/L4, session trees, agent registry. v1.6 (vLLM KV-cache offload to NVMe) becomes a research spike change with a written benchmark protocol — it gates v3.0, not v2.x. Owner: A.

---

## 5. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Plugin `.ts` unrecoverable | System's auto-capture unreproducible | Phase 1.5 fallback: rewrite from SPEC-backpack-v1.2.md against the sidecar contract, with Vitest |
| Poisoned embedding cache & zero-vector memories already persisted on studio Mac | Bad retrieval, misleading agent context | Phase 2 purge script + `needs_reembedding` re-index pass |
| Fixing L2 honesty surfaces failures previously hidden | Perceived regression | Land `logging-root-fix` first; degraded≠error semantics documented |
| Ollama migration half-landed on other machine too | Runtime ValueError there | 0.1 decision applies repo-wide; ADR-0004 communicates it |
| Spec overhead slows small fixes | Process fatigue | Lightweight bugfix proposal template (10 lines); Phase 0 exemption recorded once |
| Solo maintainer bandwidth | Phases stall | Phases sized to sessions; each change independently shippable; CI keeps main always releasable |

---

## 6. Immediate Next Actions (on your approval)

1. Approve/adjust this plan (especially the 0.1 LLM-backend decision and the version renumbering in ADR-0002).
2. Team executes Phase 0 (triage + local recovery) — surgical, itemized commits, each shown to you before push.
3. Phase 1 scaffolding lands as PR `change/governance-bootstrap`; from then on, everything is a spec.

---

*Audit trail: architect/backend/database/testing subagent reports, 2026-07-12. File references verified against working tree at commit `c16c2c0` (+5 uncommitted files).*
