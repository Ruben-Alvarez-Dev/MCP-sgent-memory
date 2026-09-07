# Capability: consolidation (delta M6)

> SUPERSEDES: M2-storage consolidation spec. Delta: activa L1→L2, L2→L3,
> L3→L4 con consolidación léxica (sin LLM).

## MODIFIED Requirements

### Requirement: MEM-01 Extractive fallback summarization (MODIFIED)
L1→L2 consolidation SHALL group L1 working memories by (scope_type, scope_id)
within a configurable time window (default: last 2 hours). Groups with >= 2
events SHALL produce an L2 episode point with lexical summary
(first N lines + count + timestamps). The consolidation SHALL be idempotent:
running it twice produces identical results (enforcement point:
L0_to_L4_consolidation._consolidate_l1_l2; test:
tests/core/test_consolidation_l1_l2.py).

#### Scenario: Multiple L1 events become one L2 episode
- GIVEN 5 L1 memories in scope "agent/frontend" within 1 hour
- WHEN consolidate() runs
- THEN one L2 episode is created with summary of all 5 events

#### Scenario: Idempotent consolidation
- GIVEN an existing L2 episode for a scope group
- WHEN consolidate() runs again
- THEN no duplicate episode is created (checked by scope_id)

### Requirement: MEM-02 Threshold promotion (MODIFIED)
L2→L3 consolidation SHALL extract entities from L2 episodes and create L3
semantic points (type=entity). Each entity's mention_count is incremented.
Entity type is inferred from naming convention (CamelCase→class/function,
UPPER_SNAKE→constant/module). The consolidation SHALL NOT create duplicate
entities (enforcement point: L0_to_L4_consolidation._consolidate_l2_l3;
test: tests/core/test_consolidation_l2_l3.py).

#### Scenario: Entity extraction from episodes
- GIVEN L2 episode content "We decided to use AuthService with JWT tokens"
- WHEN consolidate runs
- THEN entities "AuthService" (class), "JWT" (concept) are created in entities table

#### Scenario: No duplicate entities
- GIVEN entity "AuthService" already exists for scope
- WHEN consolidate runs again
- THEN mention_count is incremented, no new entity row is created

### Requirement: MEM-03 Background dream with cooldown (MODIFIED — NO-OP removed)
L3→L4 consolidation SHALL find entity co-occurrence patterns (entities that
appear together in >= 3 L3 points) and create L4 narrative summaries.
Relations between entities are recorded in the relations table. The
consolidation runs on heartbeat threshold (default: every 3600 turns)
(enforcement point: L0_to_L4_consolidation._consolidate_l3_l4;
test: tests/core/test_consolidation_l3_l4.py).

#### Scenario: Co-occurrence creates narrative
- GIVEN entities "AuthService" and "JWT" co-occur in 5+ L3 points
- WHEN consolidate runs
- THEN L4 narrative "Authentication pattern: AuthService + JWT" is created

#### Scenario: Relations are recorded
- GIVEN the above co-occurrence
- WHEN consolidate runs
- THEN a "uses" relation is created between "AuthService" and "JWT"
