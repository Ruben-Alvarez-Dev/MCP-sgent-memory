# Capability: isolation (current truth, pre-change)

> ⚠️ **SUPERSEDED — frozen pre-change baseline.** Missions M1–M5 modified this
> capability; the living truth is the delta chain in
> `openspec/changes/M*/specs/` (each gate signs what changed). Kept verbatim
> as the baseline those deltas were reviewed against.

## Purpose
Who can see whose memories today. This spec documents the current
self-asserted, partially-enforced model — including confirmed leaks — so M1's
deltas are reviewable and no leak is ever reintroduced silently.

## Requirements

### Requirement: ISO-01 Self-asserted identity (KNOWN WEAKNESS)
The system SHALL accept `agent_id`/`user_id`/`scope` as caller-supplied strings
with no authentication. There is no identity layer.

### Requirement: ISO-02 L2 threads are scope-filtered (reference implementation)
`search_conversations`, `search_fts`, and `list_threads` SHALL filter by
`agent_scope` (own + `shared`) in both Qdrant and SQLite paths.

#### Scenario: Cross-agent thread search
- GIVEN threads of `director-1`, `engineer-1`, and `shared`
- WHEN searching with `agent_scope="director-1"`
- THEN results contain own + shared threads and never `engineer-1` threads.

### Requirement: ISO-03 Reminders ignore scope (CONFIRMED LEAK L-R1)
`_get_reminders(agent_id)` SHALL return all `*.json` regardless of `agent_id`
(current behavior in `src/L5_routing/server/main.py:25`). M1 MUST close this.

### Requirement: ISO-04 Decisions retrieval ignores scope (CONFIRMED LEAK L-D1)
`_retrieve_L3_decisions` SHALL read all `*.md` files with no scope filter
(current behavior in `src/shared/retrieval/__init__.py:281-306`). M1 MUST close this.

### Requirement: ISO-05 Facts filter in Python post-search (WEAKNESS L-F1)
`search_memory` SHALL filter by `user_id` in Python after Qdrant search, with no
engine-level filter on other read paths. M1 MUST move enforcement to the engine.

### Requirement: ISO-06 Consolidation mixes scopes (CONFIRMED LEAK L-C1)
`_promote_l2_l3`/`_promote_l3_l4`/`dream` SHALL write `scope_id` values
`consolidated`/`narrative`/`dream` with no source-scope provenance. M1 MUST
deprecate these writes; only `global/merged` with provenance may exist (M5).

### Requirement: ISO-07 Vault and decisions filesystem are global (WEAKNESS L-V1)
Vault and decision files SHALL live in shared directories with no namespace
separation. M1 MUST jail them per scope.

### Requirement: ISO-08 Scoped clients exist but are unused (DEAD CODE)
`ScopedQdrantClient` and `HybridQdrantClient` SHALL exist with passing isolation
unit tests while no MCP hot path uses them. M1 MUST migrate the hot path or
delete them (no dead security code).
