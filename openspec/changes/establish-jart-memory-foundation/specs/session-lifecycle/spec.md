---
id: SPEC-session-lifecycle
title: Session lifecycle
type: spec
status: proposed
version: 0.1.0
owners: [memory, identity]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Session lifecycle

## Requirements

### Ownership

A session MUST bind immutably to territory, tenant, accountable user when
applicable, agent definition, agent instance, and initial task.

### State transitions

The normal lifecycle MUST be `active -> ending -> ended`. Revocation MUST be
possible from any non-terminal state and MUST block new captures immediately.

Scenario: an event arrives after session end. The service denies it and records no
authoritative event or index work.

### Ordering and idempotency

Every accepted event MUST receive a monotonic `session_seq`. A repeated
idempotency key MUST return the original outcome and MUST NOT duplicate events,
memories, index work, or promotions.

### Time semantics

Occurrence, ingestion, creation, update, start, end, validity, supersession, and
tombstone timestamps MUST remain distinct and use UTC RFC 3339.
