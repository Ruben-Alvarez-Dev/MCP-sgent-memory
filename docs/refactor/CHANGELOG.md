# Changelog — MCP-agent-memory Refactoring

All notable changes to the refactoring effort will be documented here.

Format: [Phase] - YYYY-MM-DD

---

## [Planning] - 2026-04-22

### Added
- Master plan document with 5-phase refactoring strategy
- Phase-specific specs and checklists
- Overall checklist tracking all 37 tasks across 5 phases
- Architecture decisions (AD-1 through AD-5)
- Risk assessment with mitigation strategies

### Architecture Decisions
- AD-1: Composition over inheritance for unified server
- AD-2: Shared QdrantClient as single source of truth
- AD-3: Structured output via Pydantic models
- AD-4: Explicit environment loading (no auto-import side effects)
- AD-5: Backward compatibility (51 tool names unchanged)

### Identified Issues (from audit)
- 23+ bare except handlers hiding bugs
- Private FastMCP API usage (`_tool_manager._tools`)
- 15+ deprecated `datetime.utcnow()` calls
- Custom LRU cache duplicating `functools.lru_cache`
- BM25 tokenizer using MD5 truncation (collision risk)
- No structured logging
- No MCP structured output or annotations
- Massive code duplication across 7 server modules

---

## [Phase 1] - 2026-04-22

### Added
- `shared/qdrant_client.py` — centralized Qdrant operations (ensure_collection, upsert, search, scroll, get, count)
- `shared/config.py` — type-safe configuration with validation (40+ env vars)
- `servers/tests/test_qdrant_client.py` — unit tests for QdrantClient
- `servers/tests/test_config.py` — unit tests for Config

### Changed
- `shared/embedding.py` — replaced custom EmbeddingCache with functools.lru_cache, added threading.Lock for thread-safe backend initialization
- `shared/env_loader.py` — removed auto-load on import (`_loaded_from = load_env()`), added `get_config()` convenience function

### Commit
- `7a3b3cc` — feat(shared): add QdrantClient and Config, refactor embedding and env_loader

---

## [Phase 2] - 2026-04-22

### Changed
- All 7 server modules refactored to use shared infrastructure
- Each module imports QdrantClient and Config from shared
- Each module exports `register_tools(mcp, qdrant, config, prefix)` function
- Removed 2516 lines of duplicated boilerplate code
- 50/51 tools refactored (verify_compliance_tool temporarily dropped from vk-cache)

### Commit
- `f71af26` — refactor(servers): all 7 modules use shared QdrantClient, Config, and register_tools()

---

## [Phase 3] - 2026-04-22

### Changed
- Unified server rewritten to use public API only
- Each module's register_tools() called directly instead of extracting from private _tool_manager
- Dynamic module loading with prefixed tool names

### Removed
- All private FastMCP API usage (`_tool_manager._tools`)

### Commit
- `7710a05` — refactor(unified): rewrite server to use public API only

---

## [Phase 4] - 2026-04-22

### Added
- Pydantic return models for all 51 tools
- MCP annotations on all tools
- `@mcp.resource()` for status endpoints

### Changed
- Tools return Pydantic models instead of JSON strings

---

## [Phase 5] - 2026-04-22

### Changed
- All `datetime.utcnow()` → `datetime.now(timezone.utc)`
- All bare excepts replaced with proper error handling + logging
- All public functions have full type hints
- BM25 tokenizer uses proper hash function

### Added
- Structured logging across all modules
- Integration tests for unified server
