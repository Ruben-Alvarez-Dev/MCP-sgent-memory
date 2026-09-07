# M9-Schema-Migration — Gate

**Date:** 2026-09-07
**Status:** ⚠️ PARTIAL / DEFERRED

## Summary
- M6+M7+M8 completed successfully (zero embedding dependencies)
- M9 schema migration deferred due to test compatibility issues
- Vector column remains as dead column (inoffensive)
- 409 tests passing, 17 skipped

## What Was Attempted
- Remove `vector` column from CREATE TABLE
- Add migration hook for existing DBs
- Update upsert signatures

## Why Deferred
- Breaking changes to test infrastructure
- Some tests depend on vector-based upsert/search
- Conservative approach: dead column is harmless

## Remaining Tasks
- [ ] Carefully remove vector column from schema
- [ ] Migrate 17 skipped tests to FTS5-only API
- [ ] Update eval fixture for 40 docs without embedding chunks
- [ ] Rewrite README architecture section
- [ ] GATE_M9 final sign-off

## Current State
- 409 passed, 0 failed, 17 skipped
- Zero embedding imports in production code
- FTS5 retrieval fully functional
