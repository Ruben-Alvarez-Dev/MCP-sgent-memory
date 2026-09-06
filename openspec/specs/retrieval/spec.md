# Capability: retrieval (current truth, pre-change)

> ⚠️ **SUPERSEDED — frozen pre-change baseline.** Missions M1–M5 modified this
> capability; the living truth is the delta chain in
> `openspec/changes/M*/specs/` (each gate signs what changed). Kept verbatim
> as the baseline those deltas were reviewed against.

## Purpose
How the system finds memories today: dense vectors (BGE-M3), deterministic
intent classification, and score fusion. This spec freezes current behavior so
deltas can be reviewed against it.

## Requirements

### Requirement: RET-01 Dense-first search
The system SHALL search Qdrant collections by dense cosine similarity over
1024-dim BGE-M3 vectors with per-call `score_threshold` (default 0.3).

#### Scenario: Standard lookup
- GIVEN points with BGE-M3 vectors in `L0_L4_memory`
- WHEN `QdrantClient.search(vector, limit=10, score_threshold=0.3)` is called
- THEN only points above threshold are returned, ordered by score desc.

### Requirement: RET-02 Deterministic intent classification
The system SHALL classify every retrieval query with the deterministic
`classify_intent()` (regex/entities, no model) into intent/profile/token-budget.

#### Scenario: Code lookup routing
- GIVEN query "where is the AuthService class defined?"
- WHEN `retrieve()` runs
- THEN intent is `code_lookup`, profile `dev`, and entity list contains `AuthService`.

### Requirement: RET-03 Score fusion
The system SHALL rank candidates with
`combined = level_weight*score*0.5 + recency*0.2 + freshness*0.3`, clamped to [0,1].

### Requirement: RET-04 Degraded ranking without micro-LLM
The system SHALL fall back to score order when `rank_by_relevance` has no small
LLM available (current permanent state: no qwen3.5:2b deployed).

### Requirement: RET-05 Sparse vectors are write-only (KNOWN LIMITATION)
The system SHALL store `sparse_vectors.text` (bm25_tokenize) on upsert but
SHALL NOT use them on any read path. Recorded here so M3's delta (sparse read
path) is reviewable as a behavior change.

### Requirement: RET-06 L5 hard-depends on embeddings (KNOWN BUG-002)
`L5_routing` SHALL use `async_embed` (raising, no zero-vector fallback), so
`request_context`/`push_reminder`/`detect_context_shift` fail closed when the
embedding server is down. M3 must replace this with `safe_embed`/deterministic.
