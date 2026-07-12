# Project context — MCP-agent-memory

> OpenSpec root. `specs/` = current truth · `changes/` = approved proposals in flight. Baseline specs are being backfilled in Phase 1 (see `docs/plan/IMPROVEMENT-PLAN.md`).

**What this is**: persistent multi-layer memory (L0 raw → L4 narrative + L5 routing) for AI coding agents. Python MCP server (53 tools, 7 `Lx_*` modules) + HTTP sidecar :8890 + OpenCode plugin (auto-triggers) + Qdrant (vectors, dim 1024) + SQLite FTS5 (threads) + bilingual ES/EN Obsidian vault.

**Stack**: Python 3.12+ (pydantic v2, httpx, MCP SDK), Qdrant, llama.cpp/Ollama (per-machine, see ADR-0004), TypeScript plugin (OpenCode), launchd (macOS services).

**Machines**: this repo runs on heterogeneous hardware (Hackintosh x86 CPU-only, Apple Silicon studio Mac). Never assume capabilities — resolve them via `shared/model_tier.py` (tier T0-T4). The hive coordinator (v3.0) exists only where the resolver enables T4.

**Conventions**: SemVer single 2.x line (hive = 3.0) · Conventional Commits, English, granular · MADR ADRs in `docs/adr/` · docs in English, replies to Rubén in Spanish · no mocks/fakes outside tests · SOLID, ports at module boundaries · surgical changes require Rubén's approval · quality gates in `docs/plan/IMPROVEMENT-PLAN.md` §3.4.

**Glossary**: "the backpack" = plugin + server system · Lx modules = L0_capture, L0_to_L4_consolidation, L2_conversations, L3_facts, L3_decisions, L5_routing, Lx_reasoning · "tier" = hardware capability class resolved at runtime.
