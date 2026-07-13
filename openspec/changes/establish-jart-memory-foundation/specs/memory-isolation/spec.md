---
id: SPEC-memory-isolation
title: Memory isolation
type: spec
status: proposed
version: 0.1.0
owners: [memory, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: ADR-0002
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Memory isolation

## Requirements

### Minimum scope

New memory MUST start in the minimum authorized scope. The service MUST distinguish
session-private, agent-private, team-private, domain-controlled,
tenant-controlled, global-golden, and external-RAG material.

### Authorized composition

Search MUST compose independent authorized views from narrow to broad. It MUST NOT
query an unscoped global index and post-filter results in application code.

Scenario: principal A knows principal B's `memory_id`. Every get, search, list,
update, correct, tombstone, delete, and promotion path denies without revealing
existence or content.

### Defense in depth

Application policy and authoritative storage controls MUST both enforce ownership
and visibility. Qdrant MUST receive mandatory server-side filters for identity,
scope, policy, and classification.

### Revocation

Revocation MUST remove access from API, bus, and derived indexes without deleting
authorized historical evidence.
