# MCP-agent-memory — Refactoring Master Plan

**Status**: PLANNING → READY FOR EXECUTION
**Created**: 2026-04-22
**Repo**: https://github.com/Ruben-Alvarez-Dev/MCP-sgent-memory

---

## 1. Problem Statement

Seven server modules (automem, autodream, vk-cache, conversation-store, mem0, engram, sequential-thinking) share ~60% identical boilerplate for Qdrant operations, embedding generation, environment loading, and MCP server initialization.

Critical issues:
- **Unified server uses private API** (`_tool_manager._tools`) — fragile, breaks on library updates
- **Massive code duplication** — each server reimplements Qdrant helpers, embedding wrappers, config loading
- **Inconsistent defaults** — modules diverge silently (e.g., QDRANT_COLLECTION)
- **No MCP structured output** — tools return JSON strings instead of typed models

## 2. Goals

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Eliminate code duplication | Shared code handles 100% of Qdrant + embedding ops |
| G2 | Unified server uses public API only | Zero `_tool_manager` references |
| G3 | MCP protocol compliance | Structured output + annotations |
| G4 | Code quality | Zero bare `except`, full type hints, structured logging |
| G5 | Testability | Each shared module has unit tests |
| G6 | No regressions | All 51 tools remain functional |

## 3. Non-Goals

- Changing memory layer architecture (L0-L4)
- Adding new MCP tools or features
- Switching from Qdrant to another vector DB
- Changing embedding model/backend system
- Rewriting install.sh

## 4. Architecture Decisions

### AD-1: Composition over Inheritance for Unified Server
Each module exports tool functions and a `register(mcp, prefix)` function.
No inheritance, no private API access.

### AD-2: Shared QdrantClient as Single Source of Truth
All Qdrant HTTP operations centralized in `shared/qdrant_client.py`.

### AD-3: Structured Output via Pydantic Models
Tools return Pydantic models instead of JSON strings.

### AD-4: Explicit Environment Loading
`env_loader.py` no longer auto-loads on import.

### AD-5: Backward Compatibility
51 tool names remain identical. External clients need zero changes.

## 5. Phases

```
Phase 1: Shared Infrastructure     (2-3 days) — eliminates duplication
Phase 2: Server Refactoring        (3-4 days) — each server uses shared infra
Phase 3: Unified Server Rewrite    (1-2 days) — public API, no private hacks
Phase 4: MCP Compliance            (1-2 days) — structured output, annotations
Phase 5: Quality & Testing         (2-3 days) — logging, type hints, tests
─────────────────────────────────────────────
Total: 9-14 days
```

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking tool names | Low | High | Keep exact names, integration test |
| MCP library API change | Medium | High | Phase 3 eliminates private API |
| Qdrant API drift | Low | Medium | Centralized client |
| Scope creep | Medium | Medium | Strict phase boundaries |

## 7. Commit Strategy

- Each logical unit = 1 commit
- 2-4 sentences in English per commit
- Push after each commit
- No WIP commits

## 8. Checklists

- [Overall Checklist](./CHECKLIST.md)
- [Phase 1](./phase-1-shared-infra.md)
- [Phase 2](./phase-2-server-refactor.md)
- [Phase 3](./phase-3-unified-server.md)
- [Phase 4](./phase-4-mcp-compliance.md)
- [Phase 5](./phase-5-quality-testing.md)
- [Changelog](./CHANGELOG.md)
