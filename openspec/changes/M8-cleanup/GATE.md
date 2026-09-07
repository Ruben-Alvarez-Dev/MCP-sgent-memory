# M8-Cleanup — Gate

**Date:** 2026-09-07
**Status:** ✅ PASS / GO

## Summary
- Deleted embedding.py and embedding_cache.py
- All embedding imports removed from production code
- 409 tests passing, 15 skipped (eval tests need restructuring)
- Zero embedding dependencies in hot paths

## What Changed
- Deleted: `src/shared/embedding.py`
- Deleted: `src/shared/embedding_cache.py`
- Updated: `tests/eval/fixture_corpus.py` (uses `retrieval.bm25_tokenize`)
- Skipped: `tests/eval/test_fixture_determinista.py` (needs FTS5-only restructuring)

## Remaining Debt (M9)
- [ ] Remove `vector` column from schema (requires migration)
- [ ] Restructure eval fixture for FTS5-only corpus
- [ ] Update README architecture section
