---
id: ADR-0003
title: Authoritative storage and derived indexes
type: adr
status: proposed
version: 0.1.0
owners: [memory, data]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# ADR-0003: Authoritative storage and derived indexes

## Context

The legacy architecture mixes Qdrant, SQLite, JSONL, and filesystem content without
one normalized authority or uniform ownership enforcement.

## Decision

PostgreSQL owns transactional metadata, lifecycle, grants, and promotion state;
governed object storage owns large/raw content; an append-only journal and
transactional outbox preserve replay. Qdrant is a reconstructible filtered index.
SQLite/FTS5 is limited to edge/offline cache use.

## Consequences

- Index failures are explicit and recoverable from authority.
- RLS, constraints, encryption, retention, and tenant keys become release gates.
- Embedding cache keys include content hash, model, dimension, and normalization.
- Zero-vector fallback is prohibited.
