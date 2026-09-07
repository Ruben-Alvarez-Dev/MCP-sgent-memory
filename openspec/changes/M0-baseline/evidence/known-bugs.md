# Known bugs (frozen as baseline; fixing belongs to later missions)

- **KNOWN-BUG-001**: `tests/app/conftest.py:18` health-checks embedding server at
  `:8081/health`, but the deployment runs it at `:8091` (see `config/.env:4`).
  Port `:8081` is occupied by an unrelated proxy (PID 882). Net effect: app suite
  always SKIPS. Owner: M2 (app suite gets rewritten for memory.db anyway).
- **KNOWN-BUG-002**: `L5_routing` uses raising `async_embed` (no zero-vector fallback),
  so `request_context`/`push_reminder`/`detect_context_shift` fail closed without
  embeddings — the only module that breaks instead of degrading. Owner: M3.
- **KNOWN-BUG-003**: `tests/core/test_llm_ranking.py::test_rank_by_relevance_top_k`
  FAILS (returns 20 items, expected ≤5) because no small LLM is deployed and the
  fallback returns unranked input. This failure IS the evidence that generative
  ranking is permanently degraded. Owner: M3 (function gets deleted; test deleted
  with it after recording this baseline).
- **Legacy skips (6)**: `test_v3_spec_features.py` — superseded spec, intentionally
  skipped. Not bugs.
