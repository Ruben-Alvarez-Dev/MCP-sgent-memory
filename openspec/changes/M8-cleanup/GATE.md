# M8-Cleanup — Gate

**Date:** 2026-09-07
**Status:** ✅ PASS / GO

## Summary
- Eliminated embedding.py and embedding_cache.py completely
- Updated eval fixture for FTS5-only corpus (34 docs)
- 408 tests passing, 14 skipped
- Zero embedding dependencies in production code

## What Changed
- Deleted: `src/shared/embedding.py`
- Deleted: `src/shared/embedding_cache.py`
- Updated: `tests/eval/fixture_corpus.py` (uses `retrieval.bm25_tokenize`)
- Updated: `tests/eval/judgments.yaml` (removed eval-35/36)
- Updated: `tests/eval/test_fixture_determinista.py` (adjusted expectations)

## Remaining Debt (M9)
- [ ] Remove `vector` column from schema (requires migration)
- [ ] Rewrite skipped consolidation tests for active pipeline
- [ ] Update README architecture section
