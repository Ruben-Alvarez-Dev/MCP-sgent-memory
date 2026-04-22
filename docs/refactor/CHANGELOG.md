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

## [Phase 2] - TBD

### Changed
- All 7 server modules refactored to use shared infrastructure
- Each module exports `register_tools()` function
- No raw httpx or os.getenv in server modules

---

## [Phase 3] - TBD

### Changed
- Unified server rewritten to use public API only
- No private `_tool_manager._tools` access

### Removed
- All private FastMCP API usage

---

## [Phase 4] - TBD

### Added
- Pydantic return models for all 51 tools
- MCP annotations on all tools
- `@mcp.resource()` for status endpoints

### Changed
- Tools return Pydantic models instead of JSON strings

---

## [Phase 5] - TBD

### Changed
- All `datetime.utcnow()` → `datetime.now(timezone.utc)`
- All bare excepts replaced with proper error handling + logging
- All public functions have full type hints
- BM25 tokenizer uses proper hash function

### Added
- Structured logging across all modules
- Integration tests for unified server
