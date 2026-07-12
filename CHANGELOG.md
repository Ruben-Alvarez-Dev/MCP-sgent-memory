# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Versions `v1.0.0`–`v2.0.0` were reconstructed from git tags and commit history
(`git tag --sort=creatordate`, `git log <tag>..<tag> --oneline`) since no changelog
existed before this file. Entries group and summarize the real commits on each
range; nothing is inferred beyond what the commit log records.

## [Unreleased]

Work in progress on `change/phase0-foundation` (Phase 0 triage + Phase 1
governance scaffolding, per `docs/plan/IMPROVEMENT-PLAN.md`). Not yet tagged;
`pyproject.toml` currently declares `2.1.0` for this line of work.

### Added

- `OllamaBackend` with typed errors and a tier-aware LLM backend factory (ADR-0004).
- Adaptive hardware/model-tier resolver (`shared/model_tier.py`, tiers T0-T4) with
  startup, periodic (TTL), and reactive re-probe triggers, plus `model_tier_status`
  MCP tool and `/api/model-tier` endpoint.
- `openspec/` governance scaffold: `project.md`, the binding verification protocol
  (`openspec/AGENTS.md`), the `model-stack` spec + JSON Schema, and change proposals
  `ollama-backend`, `adaptive-model-tier`, `control-plane-ui`.
- ADR-0007 (hexagonal/SOLID/DRY enterprise architecture, strangler migration to
  `domain/ports/adapters/app/runtime`) and ADR-0008 (auto-started Web + TUI control
  plane, Phase 3-bis).
- `install/pull-models.sh` and a fully documented `.env.example` aligned with the
  Ollama/tier defaults.
- Retroactive TDD evidence files verifying the `ollama-backend` and
  `adaptive-model-tier` iterations against the real implementation.

### Changed

- `L3_facts` and `L5_routing` migrated to `safe_embed` and async embeddings with
  typed result models.
- Root `CLAUDE.md`, session handoff, and `/loop` orchestration prompt rewritten for
  the spec-driven governance model.
- Branch/fork+PR workflow documented: work happens on `change/phase0-foundation`
  (fork `manu-alvarez/MCP-agent-memory`, PR #3), merge to `main` only on Rubén's
  approval.
- README truth pass: real directory tree, no `launchd`/plugin/`etc/` claims, test
  count corrected to 209.

### Fixed

- `_verify_stale`: invalid Qdrant filter syntax, unconditional status overwrite,
  and `vector=None` upsert replaced with a payload-only `set_payload` update.
- `install/bootstrap.sh`: `set -e` swallowing build failures, wrong SIGINT exit
  code, warning counter never incrementing, wrong build-failure attribution, and
  `write_status` not degrading gracefully on I/O errors.
- `.gitignore`: literal `$HOME/` entry corrected to the intended `.memory/` pattern.

### Removed

- Dead `VAULT_PATCHES.json` and the legacy `etc/` directory.

## [2.0.0] - 2026-05-03

### Added

- Bilingual ES/EN vault with an auto-serialization daemon, `Lx_TYPE_NNNN` naming
  scheme, and `FOLDER_MAP`.
- SQLite + FTS5 conversation store with multi-agent isolation, timeline, and MCP
  HTTP transport.
- Continuous knowledge verification (v1.4) and research docs (context-window
  extension, agent-memory landscape).
- Installer: install/update/repair mode detection, automatic backup before
  updates, update mode with data preservation.
- Auto-download of Qdrant and auto-compile of `llama-server` with Metal support;
  curl-based install without a prior clone.
- Backpack enforcement plugin v1.2 and smart context injection v1.3; OpenCode
  adapter moved into the repo as the first in-repo adapter.

### Changed

- Complete rename to the `Lx` naming scheme across modules, config fields, and
  install scripts; all documentation translated to English.
- LLM backend unified on `llama.cpp` only, removing the `ollama`/`lmstudio`
  backends present at the time (revisited in `[Unreleased]`).
- Default install path standardized to `~/MCP-servers/MCP-agent-memory`.

### Fixed

- `verify-memories` now uses `set_payload` instead of a full upsert.
- Silent `xiaomi-mimo` URL leak in config/health/embedding defaults.
- LLM backend auto-detection for an externally running server.

### Removed

- Residual `.gitkeep` vault placeholder files.

## [1.3.0] - 2026-04-23

### Added

- Batch embedding via the `/v1/embeddings` API.
- Score-threshold filtering (E01) and async dream consolidation (E02).
- Sprint 1-3: batch upsert, smart truncation, observability, layer compaction,
  status standardization, prefetch heartbeat.
- E10: Q8 model upgrade — +32% quality gap, 4x faster latency.

### Changed

- Qdrant `data/` directory added to `.gitignore`.

### Fixed

- Search scores now included in `mem0` and conversation-store results.

## [1.2.1] - 2026-04-23

### Added

- Root `install.sh` with `curl | bash` support.
- Comprehensive 8-step visual installer checklist.

### Changed

- `embedding_cache` untracked and added to `.gitignore`.

### Fixed

- Lazy initialization moved inside the MCP event loop instead of blocking on
  `asyncio.run()`.
- Server URL typo in the root installer.

## [1.2.0] - 2026-04-23

### Added

- Full source code, tests, scripts, and README committed (merge of remote
  v1.1.1 work with local documentation and fixes).

### Fixed

- `search_decisions` token matching, vault folder whitelist, `sequential_thinking`
  quality, `search_memory` validation.
- `.gitignore` and `.env` `VAULT_PATH` handling.
- `thinking` tool now returns a thought list for CLI adapter compatibility.

## [1.1.1] - 2026-04-23

### Added

- Unified MCP server architecture: shared `QdrantClient`, `Config`, and
  `register_tools()` across all 7 modules.
- MCP structured output and annotations on all 50 tools.
- Bundled offline wheels for dependency installation; BM25 tokenizer hash fix
  with an integration test for the unified server.

### Changed

- 5-phase refactor: unified server rewritten to use the public API only;
  modular SOLID installer architecture with dependency fallback.
- Renamed `MCP-servers/` to `servers/`.

### Fixed

- 32-fix industrial security audit across 10 dimensions.
- Installer made self-contained with inline fallbacks for services and
  verification; embedding installation completed.

## [1.1.0] - 2026-04-20

### Added

- Strict embedding validation and spec contract.
- Real health checks and port auto-detection (`find_free_port`) in the
  installer.

### Fixed

- Placeholder embed and retrieval implementations replaced with real
  `shared.embedding` calls.
- Default embedding dimension corrected in docstrings.

### Removed

- Stale `engram-facade` and `context7-proxy` references from README.

## [1.0.0] - 2026-04-19

Initial tagged release.

### Added

- Hierarchical memory system L0-L5 with a unified shared package (embedding,
  Qdrant client, env loader).
- Plandex Fusion: 6 capabilities, 12 specs, autonomous Ralph loop.
- Input sanitization layer (`shared/sanitize.py`) with invisible-character
  stripping (supplementary planes, soft hyphen).
- End-to-end benchmark suite (62 tests across all servers).

### Changed

- Renamed `MCP-memory-server` to `MCP-agent-memory`; `servers/` restructured
  with a proper `.gitignore`.
- All servers load `shared/env_loader` before reading configuration.

### Fixed

- Qdrant hybrid search uses `/points/query` instead of the removed
  `/search/sparse` endpoint (404).
- Retrieval scores, filename sanitization, `mem0` `user_id` filter.
- `launchd` plist, model pack paths, `llama-server` configuration.

### Removed

- `steering/` (agent loop moved to the `CLI-agent-memory` repo).

[Unreleased]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.3.0...v2.0.0
[1.3.0]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/releases/tag/v1.0.0
