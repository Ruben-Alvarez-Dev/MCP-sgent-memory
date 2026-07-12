# Spec delta — embedding-pipeline (from change `fix-embedding-truncation`)

> No `openspec/specs/embedding-pipeline/` baseline exists yet as of this change (only `model-stack` and the in-progress `l0-capture` baseline are present under `openspec/specs/`). This delta is written as a **self-contained target end-state description** per the planning instructions for this change, and MUST be reconciled (folded in as ADDED/MODIFIED requirements against whatever baseline lands) once the Phase 1 `embedding-pipeline` baseline spec exists.

## Capability: embedding correctness

The system SHALL embed the full content it is given, subject only to one explicit, logged, upstream safety cap — never an undisclosed additional truncation on any cached or re-computed path.

### Requirement: full-text embedding

The text passed to the active `EmbeddingBackend.embed()` call SHALL be identical to the text passed into `get_embedding()`, up to the single documented safety cap (`smart_truncate` at `EMBEDDING_DIM`-independent 2000 chars, or its successor constant). No intermediate caching layer (in-memory LRU, persistent SQLite) SHALL further shorten the text before it reaches the backend.

#### Scenario: text longer than the in-memory cache's former erroneous limit

- **GIVEN** a text of length between 201 and 2000 characters
- **WHEN** `get_embedding(text)` is called
- **THEN** the backend's `embed()` method receives the text unmodified (full length, not truncated to 200 characters)

### Requirement: loud truncation

Any truncation applied to text before embedding (the 2000-char safety cap) SHALL be logged at `WARNING` level with the original and post-truncation lengths, satisfying `openspec/AGENTS.md` §1 ("no silent degradation").

#### Scenario: oversized text triggers a logged truncation

- **GIVEN** a text longer than the safety cap (2000 characters)
- **WHEN** `get_embedding(text)` is called
- **THEN** exactly one `WARNING`-level log record is emitted, containing the original length and the truncated length
- **AND** the backend receives the truncated (not original) text, consistent with the documented cap

#### Scenario: text within the cap produces no truncation log

- **GIVEN** a text of length ≤2000 characters
- **WHEN** `get_embedding(text)` is called
- **THEN** no truncation-related `WARNING` log record is emitted

## Capability: embedding cache integrity

The persistent embedding cache SHALL never serve a vector computed by a different model or dimensionality than the one currently active, and SHALL NOT grow without bound.

### Requirement: model- and dimension-scoped cache keys

Every persistent cache entry SHALL be keyed by a function of `(model_id, dim, text)`, where `model_id` uniquely identifies the concrete embedding model/backend configuration in use (see `EmbeddingBackend.model_id`) and `dim` is the embedding's vector dimensionality.

#### Scenario: model swap does not serve a stale vector

- **GIVEN** a cache entry was written for text `T` under `(model_id="A", dim=384)`
- **WHEN** `get_embedding(T)` is later called with the active backend resolving to `(model_id="B", dim=1024)`
- **THEN** the cache lookup for `(model_id="B", dim=1024, T)` is a miss
- **AND** the embedding is recomputed against the currently active backend, not served from the stale `(A, 384)` entry

### Requirement: bounded cache size via LRU eviction

The persistent cache SHALL enforce a maximum row count (`EMBEDDING_CACHE_MAX_ROWS`, default 50000). When a write would exceed the cap, the least-recently-accessed rows SHALL be evicted first, down to the cap.

#### Scenario: cache at capacity evicts the oldest-accessed entry

- **GIVEN** the cache holds exactly `EMBEDDING_CACHE_MAX_ROWS` entries
- **WHEN** a new, distinct entry is written via `cache_set`
- **THEN** the total row count remains at `EMBEDDING_CACHE_MAX_ROWS`
- **AND** the entry with the oldest `last_accessed_at` timestamp before the write is no longer present

### Requirement: recoverable purge of poisoned entries

An operator-invoked, idempotent script SHALL exist to purge the entire persistent embedding cache, backing up the database file before mutating it, and SHALL support a dry-run mode that performs no mutation.

#### Scenario: dry-run reports without mutating

- **GIVEN** a populated embedding cache database
- **WHEN** the purge script is invoked with `--dry-run`
- **THEN** the row count and the database file are unchanged
- **AND** no backup file is created

#### Scenario: real run backs up then empties the cache

- **GIVEN** a populated embedding cache database
- **WHEN** the purge script is invoked without `--dry-run`
- **THEN** a backup file is created containing the pre-purge row count
- **AND** the live `embeddings` table is empty afterward
