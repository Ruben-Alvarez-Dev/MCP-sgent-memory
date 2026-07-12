# Project context — MCP-agent-memory

> OpenSpec root. `specs/` = current truth · `changes/` = approved proposals in flight. Baseline `specs/` written in Phase 1 (item 1.1) from the audits in `docs/plan/IMPROVEMENT-PLAN.md` §2 — covers l0-capture, l2-conversations, l3-facts, http-sidecar, embedding-pipeline, vault, model-stack; remaining Lx modules (l0-to-l4-consolidation, l3-decisions, l5-routing, lx-reasoning) and plugin-orchestrator are tracked as follow-up.

**What this is**: persistent multi-layer memory (L0 raw → L4 narrative + L5 routing) for AI coding agents. Python MCP server (53 tools, 7 `Lx_*` modules) + HTTP sidecar :8890 + OpenCode plugin (auto-triggers) + Qdrant (vectors, dim 1024) + SQLite FTS5 (threads) + bilingual ES/EN Obsidian vault.

**Stack**: Python 3.12+ (pydantic v2, httpx, MCP SDK), Qdrant, llama.cpp/Ollama (per-machine, see ADR-0004), TypeScript plugin (OpenCode), launchd (macOS services).

**Architecture — current reality vs target**: today the code is flat per-module (`src/L*_*/server/main.py`, each with a `register_tools()` entrypoint loaded by `importlib` into `src/unified/server/main.py`); I/O (Qdrant, SQLite, filesystem, embedding backends) is called directly from handler functions, not behind ports. Four overlapping process entrypoints exist (`unified/server/main.py` stdio + HTTP sidecar thread, `backpack.py` standalone sidecar daemon, `main_http.py` streamable-HTTP MCP transport, `gateway.py` dead code — requires undeclared `aiohttp`). **Target** (ADR-0007, binding going forward): hexagonal ports & adapters, one daemon (`backpack.py`, ADR-0005) owning `:8890`; strangler migration — every module touched moves toward `domain/ports/adapters/app/runtime`, no cross-imports between `Lx_*` modules, abstraction at I/O/policy boundaries only.

**Machines**: this repo runs on heterogeneous hardware (Hackintosh x86 CPU-only, Apple Silicon studio Mac). Never assume capabilities — resolve them via `shared/model_tier.py` (tier T0-T4). The hive coordinator (v3.0) exists only where the resolver enables T4.

**Conventions**: SemVer single 2.x line (hive = 3.0) · Conventional Commits, English, granular · MADR ADRs in `docs/adr/` · docs in English, replies to Rubén in Spanish · no mocks/fakes outside tests · SOLID, ports at module boundaries · surgical changes require Rubén's approval · quality gates in `docs/plan/IMPROVEMENT-PLAN.md` §3.4.

**Glossary**: "the backpack" = plugin (`backpack-orchestrator.ts`, not yet recovered into this repo — Phase 1 item 1.5) + server system · Lx modules = L0_capture, L0_to_L4_consolidation, L2_conversations, L3_facts, L3_decisions, L5_routing, Lx_reasoning · "tier" = hardware capability class resolved at runtime · "sidecar" = the HTTP API on `:8890` (`shared/api_server.py`) that lets the plugin trigger MCP tool functions without an LLM in the loop.
