---
id: SPEC-promotion-workflow
title: Promotion workflow
type: spec
status: proposed
version: 0.1.0
owners: [memory, governance, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: ADR-0004
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Promotion workflow

## Requirements

### Consequence boundary

Moving knowledge to a broader scope MUST require a promotion case. No API, database,
index, bus, or model path MAY write directly to a broader governed scope.

### Validation and decision

The case MUST record source version, target scope, provenance, evidence hashes,
deduplication, classification, redaction, freshness, policy, required gates,
decisions, and audit hash. Triumvirate and Guardian/HITL gates MUST be selected by
consequence and sensitivity.

### Materialization

Approval MUST create a derived version with immutable lineage and independent
policy. It MUST NOT mutate the source version's scope.

Scenario: a global promotion is revoked. The global derived view is withdrawn while
the authorized private source and decision evidence remain intact.

### Privacy

Promotion audit MUST store actor, policy, decision, and cryptographic hashes. It
MUST NOT contain raw memory content by default.
