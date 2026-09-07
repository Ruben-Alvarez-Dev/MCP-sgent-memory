# Capability: retrieval (delta M6)

> SUPERSEDES: M3-retrieval spec. Delta: replaces dense search with FTS5
> lexical search + entity graph boost.

## MODIFIED Requirements

### Requirement: RET-01 Dense-first search (MODIFIED → FTS5-first)
The system SHALL search `points_fts` via FTS5 MATCH with BM25 ranking,
expanded by synonym dictionary. Metadata filters (agent_scope, layer) are
applied in the SQL WHERE clause. Entity graph boost (+0.2 per overlapping
entity) is applied post-FTS5. Dense cosine search is REMOVED
(enforcement point: retrieval._fts_search; tests:
tests/core/test_retrieval_fts5.py).

#### Scenario: FTS5 finds related content
- GIVEN content "JWT authentication middleware for user sessions"
- WHEN querying "how to auth users"
- THEN FTS5 expands "auth"→"authentication|jwt|token" and finds the content

#### Scenario: FTS5 with scope filter
- GIVEN points from scopes "shared" and "director-1"
- WHEN agent "engineer-1" searches
- THEN only "shared" results are returned (scope filter in SQL WHERE)

### Requirement: RET-03 Score fusion (MODIFIED)
Ranking is now: `combined = fts_rank * 0.6 + entity_boost * 0.3 + recency * 0.1`
(clamped to [0,1]). No more dense+hash fusion (enforcement point:
retrieval._rank_and_fuse; test: tests/core/test_retrieval_ranking.py).

#### Scenario: Entity boost changes ranking
- GIVEN two FTS5 results with equal rank, one matching query entities
- WHEN ranked
- THEN the entity-matching result ranks higher

### Requirement: RET-05 Sparse vectors (SUPERSEDED)
Sparse vectors (bm25_tokenize) are REMOVED. FTS5 replaces the lexical channel.

### Requirement: RET-06 L5 degradation without embeddings (SUPERSEDED)
Embedding dependency is REMOVED entirely. L5 tools work without any embedding
backend (enforcement point: L5_routing server; test:
tests/core/test_l5_no_embedding.py).

## ADDED Requirements

### Requirement: RET-07 FTS5 query with synonym expansion (ADDED)
Every retrieval query SHALL be expanded through the synonym dictionary before
being sent to FTS5 MATCH. Technical terms in both EN and ES are expanded to
include common aliases. The expansion is applied at the query string level
(enforcement point: retrieval._expand_query; test:
tests/core/test_query_expansion.py).

#### Scenario: Synonym expansion increases recall
- GIVEN synonym map: "db" → "database|sqlite|postgres"
- WHEN query is "where is the db config"
- THEN FTS5 searches for "where is the database sqlite postgres config"

#### Scenario: Empty expansion preserves original terms
- GIVEN a query with no known synonyms
- WHEN expand_query runs
- THEN the original query terms are preserved and FTS5 runs normally

### Requirement: RET-08 Entity graph boost in ranking (ADDED)
After FTS5 retrieval, each result SHALL be boosted by the number of entity
overlaps between the query entities and the result's extracted entities
(+0.2 per overlap, max +1.0). This promotes results that share domain-specific
terminology with the query (enforcement point: retrieval._entity_boost;
test: tests/core/test_entity_boost.py).

#### Scenario: Entity overlap boosts relevant results
- GIVEN query contains entity "AuthService"
- GIVEN result A has entity "AuthService" (score 0.5), result B does not (score 0.5)
- WHEN entity boost is applied
- THEN result A ranks higher than B

#### Scenario: Entity boost clamped to [0,1]
- GIVEN a result with very low FTS5 score but high entity overlap
- WHEN boost is applied
- THEN combined score is clamped to [0, 1]

### Requirement: RET-09 Zero embedding dependency (ADDED)
The retrieval pipeline SHALL function without any embedding backend, network
service, or model file. All retrieval SHALL be pure lexical (FTS5) +
metadata filtering + entity graph boosting (enforcement point: retrieval.retrieve;
test: tests/core/test_no_embedding_required.py).

#### Scenario: Retrieval works with no services running
- GIVEN no llama-server, no ollama, no HTTP endpoints
- WHEN retrieve() is called
- THEN it returns results without any embedding call

#### Scenario: All embedding imports are removed
- GIVEN the codebase after M6
- WHEN `grep -rn "from shared.embedding\|import embedding" src/` runs
- THEN zero references remain
