---
id: SPEC-storage-authority
title: Storage authority
type: spec
status: proposed
version: 0.1.0
owners: [memory, data]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: ADR-0003
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Storage authority

## Requirements

### Sources of truth

Transactional metadata, versions, grants, and promotion state MUST be authoritative
in PostgreSQL. Large/raw content MUST be authoritative in governed encrypted object
storage. The journal and transactional outbox MUST support replay.

### Derived indexes

Qdrant and edge SQLite/FTS5 MUST be reconstructible and MUST NOT grant authority.
Index state MUST be reported as pending, indexed, or failed.

Scenario: the authoritative transaction commits and Qdrant is unavailable. The
service returns a truthful pending/failed index state and retries from outbox; it
does not report fully indexed success.

### Embedding integrity

Embedding cache keys MUST include content hash, model identifier, dimension, and
normalization version. Failure MUST NOT create or persist a zero vector.

### Recovery

Rebuild MUST reconcile counts and hashes from authority and journal. Ownerless or
ambiguous legacy material MUST enter quarantine.
