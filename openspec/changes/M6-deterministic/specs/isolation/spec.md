# Capability: isolation (delta M6)

## ADDED Requirements

### Requirement: ISO-18 Entity and relation reads are scope-gated (ADDED)
All reads from `entities` and `relations` tables SHALL include an engine-level
`agent_scope` filter in the SQL WHERE clause. Cross-scope entity access via
relations is forbidden (enforcement point: memory_db.get_entities,
memory_db.get_relations; test: tests/adversarial/test__M6__entity_isolation.py).

#### Scenario: Entities are scope-isolated
- GIVEN entity "AuthService" in scope "director-1"
- WHEN agent "engineer-1" calls get_entities()
- THEN "AuthService" is NOT returned

#### Scenario: Relations respect scope
- GIVEN relation between entities in scope "director-1"
- WHEN agent "engineer-1" calls get_relations()
- THEN the relation is NOT returned
