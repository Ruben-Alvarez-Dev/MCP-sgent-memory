# Capability: retrieval (delta M3)

## MODIFIED Requirements

### Requirement: RET-01 Dense-first search over memory.db (was: Qdrant collections)
The system SHALL search memory.db collections by dense cosine over 1024-dim
vectors with per-call `score_threshold` (default 0.3); rows whose embedding
failed are scored against deterministic hash-vectors (STO-05). Engine filters
(scope/user/layer) are enforced in SQL before scoring (enforcement point:
MemoryDB.search; test: tests/core/test_memory_db.py).

#### Scenario: Standard lookup
- GIVEN points with dense vectors in `L0_L4_memory`
- WHEN `MemoryDB.search(vector, limit=10, score_threshold=0.3, filter=...)`
- THEN only points at/above threshold are returned, ordered by score desc
  (ties broken by id asc for determinism).

### Requirement: RET-04 Ranking is deterministic score fusion (was: LLM fallback)
The system SHALL rank candidates exclusively with the deterministic fusion
`combined = level_weight*score*0.5 + recency*0.2 + freshness*0.3` (clamped to
[0,1]). Generative/LLM re-ranking is PERMANENTLY removed (hard constraint:
zero local models). `rank_by_relevance` SHALL NOT exist
(enforcement point: retrieval._rank_and_fuse; test: tests/core/test_no_llm_ranking.py).

#### Scenario: No LLM ranking path remains
- GIVEN the M3 branch
- WHEN `grep -rn rank_by_relevance src/ tests/` runs (excluding specs)
- THEN zero references remain and `intent.needs_ranking` has no consumer.

### Requirement: RET-05 Sparse vectors are read (was: write-only)
`MemoryDB.search` SHALL accept `sparse_query` (Qdrant-format token dict) and
`sparse_weight` (default 0.3), computing a sparse cosine per candidate from
its stored `sparse_json` and fusing: `final = (1-w)*dense + w*sparse`
(score_source reflects components; enforcement point: memory_db fusion;
tests: tests/core/test_sparse_fusion.py).

#### Scenario: Lexical boost changes ranking
- GIVEN two rows with equal dense scores, one sharing query tokens
- WHEN searching with sparse_query and w=0.3
- THEN the token-sharing row ranks first and reports `dense+sparse`.

#### Scenario: Malformed sparse query fails closed
- GIVEN `sparse_query={"indices": ["x"], "values": []}`
- WHEN search runs
- THEN ValueError is raised and no rows are scanned.

#### Scenario: Corrupt stored sparse_json degrades gracefully
- GIVEN a row whose sparse_json is invalid JSON
- WHEN search with sparse_query runs
- THEN the row keeps its dense score with `sparse_score=0` and search succeeds.

### Requirement: RET-06 L5 degrades deterministically without embeddings (was: hard dependency)
`push_reminder` and `detect_context_shift` SHALL fall back to deterministic
SHA-256 hash vectors when the embedding backend raises, logging a WARN; the
tools SHALL succeed (degraded) and never fail on embedding outage
(enforcement point: L5 `_embed_or_hash`;
test: tests/adversarial/test__M3__l5_degradation.py).

#### Scenario: Embedding outage does not break reminders
- GIVEN `async_embed` raises (server down)
- WHEN `push_reminder(query, reason, agent_id)` runs
- THEN a reminder is stored with hash-vector sources and a WARN was logged.

#### Scenario: Identical queries are stable without embeddings
- GIVEN the outage above
- WHEN `detect_context_shift` compares two identical queries
- THEN similarity is 1.0 and shift_detected is False.

## ADDED Requirements

### Requirement: RET-07 Deterministic tie-breaking (ADDED)
When fused scores tie, ordering SHALL be by id ascending — retrieval results
SHALL be reproducible run-to-run (enforcement point: MemoryDB.search sort;
test: tests/core/test_sparse_fusion.py::test_tie_break_is_deterministic).
