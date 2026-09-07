# Capability: isolation (delta M2)

## MODIFIED Requirements

### Requirement: ISO-05 Facts filtering is engine-level (was: Python post-search)
`search_memory`/`get_all_memories`/`delete_memory` (L3_facts) and every dense
read path SHALL pass the scope/user filter INTO `MemoryDB.search/scroll/get`,
which enforces it in the SQL WHERE clause with bound parameters. Python-side
filtering of already-fetched rows is FORBIDDEN (enforcement point: memory_db
WHERE; test: tests/adversarial/test__ISO05__engine_filter.py, cases A3/A10).

#### Scenario: Cross-user fact search returns nothing foreign
- GIVEN facts from users `u1` and `u2`
- WHEN `search_memory(query, user_id="u1")` runs
- THEN `u2` rows are filtered by the engine (no foreign row is scored in
  Python) and results contain only `u1` rows.

#### Scenario: Filter bypass attempt (A10)
- GIVEN a caller passing `filter={"must":[{"key":"user_id","match":{"value":null}}]}`
- WHEN search runs
- THEN the filter key/value is validated and the search fails closed
  (ScopeRequired/ValueError), returning zero rows from an unfiltered scan.

### Requirement: ISO-06 Consolidation stops writing mixed scopes (was: CONFIRMED LEAK L-C1)
`_promote_l2_l3`, `_promote_l3_l4` and `dream` SHALL NOT write points with
`scope_id` values `consolidated`/`narrative`/`dream`. The operations SHALL
become logged no-ops (WARN with request id) until M5 implements provenance
(enforcement point: L0_to_L4_consolidation handlers;
test: tests/adversarial/test__M2__consolidation_noop.py::test_no_mixed_scope_writes).

#### Scenario: Promotion attempts write nothing foreign
- GIVEN a consolidation run over scoped conversations
- WHEN promotions execute
- THEN zero rows with mixed scope_id values exist in `points` afterwards.

### Requirement: ISO-07 Vault/decisions jailed per scope (was: WEAKNESS L-V1)
Every filesystem write/read for vault, decisions and reminders SHALL traverse
`scope_jail_path`, resolving symlinks and rejecting escapes fail-closed
BEFORE touching the filesystem (enforcement point: scope.py jail;
tests: tests/adversarial/test__M2__fs_jail.py, cases A5/A6/A10).

#### Scenario: Symlink escape rejected
- GIVEN `data/vault/link` is a symlink to `/tmp/out`
- WHEN writing via `scope_jail_path(base, "shared", "link/x.txt")`
- THEN `ScopeError` is raised and `/tmp/out` is untouched.

### Requirement: ISO-08 Dead scoped clients deleted (was: DEAD CODE)
`src/shared/scoped_qdrant.py`, `src/shared/hybrid_qdrant.py`,
`src/shared/qdrant_client.py` and `src/shared/qdrant_factory.py` SHALL NOT
exist, together with their dedicated tests; no module SHALL import them
(enforcement point: repository state; test: tests/core/test_no_qdrant.py).

#### Scenario: No qdrant imports survive
- GIVEN the M2 branch
- WHEN `grep -ri qdrant src/` runs (excluding this spec and logs)
- THEN zero Python references remain.

## ADDED Requirements

### Requirement: ISO-11 Filter keys validated (ADDED)
`MemoryDB` SHALL validate filter keys against `^[a-z_][a-z0-9_]*$` and SHALL
bind every value as a SQL parameter, making filter-injection impossible
(enforcement point: memory_db filter translation;
test: tests/adversarial/test__M2__filter_injection.py, case A14).

#### Scenario: Injection via key/value rejected
- GIVEN filter keys like `user_id) --` or values like `' OR 1=1 --`
- WHEN search/scroll runs
- THEN a ValueError is raised (key) or the value is matched literally
  (bound param), yielding zero unauthorized rows.

### Requirement: ISO-12 Writes fail closed without scope default (ADDED)
New dense writes SHALL require an explicit `agent_scope` in payload; when
absent, `MemoryDB.upsert` SHALL inject `agent_scope="shared"` and log INFO —
global-implicit defaults are forbidden (enforcement point: memory_db upsert;
test: tests/core/test_memory_db.py::test_default_scope_is_shared).

#### Scenario: Scopeless write lands in shared
- GIVEN an upsert without agent_scope
- WHEN the row is read back by another agent with scope `director-1`
- THEN the row is visible (shared) and its payload declares `agent_scope=shared`.
