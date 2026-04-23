# MCP-agent-memory — Refactoring Master Checklist

**Last Updated**: 2026-04-22
**Overall Status**: NOT STARTED

---

## Phase 1: Shared Infrastructure
- [x] Create `shared/qdrant_client.py` — centralized Qdrant HTTP operations
- [x] Create `shared/config.py` — centralized configuration with validation
- [x] Refactor `shared/embedding.py` — replace custom cache with `functools.lru_cache`, fix global state
- [x] Refactor `shared/env_loader.py` — remove auto-load on import
- [x] Unit tests for shared/qdrant_client.py
- [x] Unit tests for shared/config.py
- [ ] Phase 1 acceptance: all existing tests pass, zero duplication of Qdrant/embedding code in shared/

## Phase 2: Server Refactoring
- [x] Refactor automem → uses QdrantClient + Config + register_tools()
- [x] Refactor autodream → uses QdrantClient + Config + register_tools()
- [x] Refactor vk-cache → uses QdrantClient + Config + register_tools()
- [x] Refactor conversation-store → uses QdrantClient + Config + register_tools()
- [x] Refactor mem0 → uses QdrantClient + Config + register_tools()
- [x] Refactor engram → uses Config + register_tools()
- [x] Refactor sequential-thinking → uses Config + register_tools()
- [x] Each module exports `register_tools(mcp, qdrant, config, prefix)` function
- [ ] Phase 2 acceptance: each server runs standalone, 51 tools still work

## Phase 3: Unified Server Rewrite
- [x] Rewrite `unified/server/main.py` — no `_tool_manager._tools` access
- [x] Each module's `register_tools()` called directly
- [x] Remove all private API usage
- [x] Phase 3 acceptance: unified server loads 7/7 modules, 50 tools, zero private API refs

## Phase 4: MCP Compliance
- [x] Add Pydantic return models for all tools
- [x] Add MCP annotations (readOnlyHint, destructiveHint, etc.)
- [x] Implement resource()` for status endpoints
- [x] Phase 4 acceptance: tools return structured output, annotations present

## Phase 5: Quality & Testing
- [ ] Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`
- [ ] Replace all bare `except:` with proper error handling + logging
- [ ] Add structured logging to all modules
- [x] Full type hints (all tools have typed returns) on all public functions
- [x] Fix BM25 tokenizer hash (use proper hashing, not MD5 truncation)
- [x] Integration test: unified server starts, all 51 tools callable
- [ ] Phase 5 acceptance: zero bare excepts, full type hints, all tests pass

## Completion Criteria
- [ ] All 5 phases complete
- [ ] All 51 tools functional
- [ ] No private API usage
- [ ] No code duplication
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Pushed to GitHub
