# Capability: isolation (delta M5)

## ADDED Requirements

### Requirement: ISO-16 Reserved trunk scope is approval-gated (ADDED)
Writes into the trunk scope `merged` SHALL be rejected by the engine
(`ScopeError`, zero I/O) unless the call explicitly passes
`allow_reserved_scope=True` AND the payload contains a non-empty
`approved_by` (human identity) AND a non-empty `provenance` list of
`{from_scope, point_id}` entries. Automatic promotions SHALL remain no-ops
(ISO-06 M2). Enforcement point: MemoryDB upsert guard;
tests: tests/adversarial/test__M5__trunk.py (A11/A12), tests/core/test_trunk.py.

#### Scenario: Automatism cannot write the trunk (A11)
- GIVEN the consolidation module attempting a direct upsert to `merged`
- WHEN no approval flag/payload is provided
- THEN ScopeError is raised and zero rows exist in scope `merged`.

#### Scenario: Trunk rows always carry provenance (A12)
- GIVEN any row with `agent_scope="merged"`
- WHEN inspecting its payload
- THEN `approved_by` and a non-empty `provenance` are present (constructor
  makes the alternative unrepresentable).

### Requirement: ISO-17 Sidecar HTTP token gate (ADDED)
When `MEMORY_HTTP_TOKEN` is set, every Backpack sidecar endpoint SHALL require
a matching `X-Memory-Token` header (constant-time compare) and SHALL answer
401 otherwise. When unset, endpoints behave as before and a WARN is logged at
startup (enforcement point: api_server request handler;
test: tests/adversarial/test__M5__trunk.py::test_sidecar_token_gate).

#### Scenario: Missing header rejected
- GIVEN MEMORY_HTTP_TOKEN set on the sidecar
- WHEN a request arrives without X-Memory-Token
- THEN the response is 401 and no handler logic executes.

## MODIFIED Requirements

### Requirement: ISO-06 Trunk merges are human-approved with provenance (was: no-op deferral)
The trunk read channel SHALL expose `merged`-scope rows to every agent
(retrieval IN-clause includes `merged` — A16). The write channel SHALL be
exclusively `approve_promotion(point_ids, approved_by)` on the consolidation
server, which SHALL copy source points into `merged` with full provenance and
mark sources `merged_into` (enforcement point: L0_to_L4 + memory_db guard;
tests: tests/core/test_trunk.py, adversarial A16).

#### Scenario: Approved merge is visible to every agent (A16)
- GIVEN a merged row created via approve_promotion
- WHEN agents with different own scopes retrieve
- THEN the merged content is available to all of them.
