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
- [ ] Refactor automem → uses QdrantClient + BaseServer pattern
- [ ] Refactor autodream → uses QdrantClient + BaseServer pattern
- [ ] Refactor vk-cache → uses QdrantClient + BaseServer pattern
- [ ] Refactor conversation-store → uses QdrantClient + BaseServer pattern
- [ ] Refactor mem0 → uses QdrantClient + BaseServer pattern
- [ ] Refactor engram → uses QdrantClient + BaseServer pattern
- [ ] Refactor sequential-thinking → uses QdrantClient + BaseServer pattern
- [ ] Each module exports `register_tools(mcp, qdrant, prefix)` function
- [ ] Phase 2 acceptance: each server runs standalone, 51 tools still work

## Phase 3: Unified Server Rewrite
- [ ] Rewrite `unified/server/main.py` — no `_tool_manager._tools` access
- [ ] Each module's `register_tools()` called directly
- [ ] Remove all private API usage
- [ ] Phase 3 acceptance: unified server loads 7/7 modules, 51 tools, zero private API refs

## Phase 4: MCP Compliance
- [ ] Add Pydantic return models for all tools
- [ ] Add MCP annotations (readOnlyHint, destructiveHint, etc.)
- [ ] Implement `@mcp.resource()` for status endpoints
- [ ] Phase 4 acceptance: tools return structured output, annotations present

## Phase 5: Quality & Testing
- [ ] Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`
- [ ] Replace all bare `except:` with proper error handling + logging
- [ ] Add structured logging to all modules
- [ ] Full type hints on all public functions
- [ ] Fix BM25 tokenizer hash (use proper hashing, not MD5 truncation)
- [ ] Integration test: unified server starts, all 51 tools callable
- [ ] Phase 5 acceptance: zero bare excepts, full type hints, all tests pass

## Completion Criteria
- [ ] All 5 phases complete
- [ ] All 51 tools functional
- [ ] No private API usage
- [ ] No code duplication
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Pushed to GitHub
