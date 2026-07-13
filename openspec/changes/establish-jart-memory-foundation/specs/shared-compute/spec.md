---
id: SPEC-shared-compute
title: Shared territorial compute
type: spec
status: proposed
version: 0.1.0
owners: [memory, inference, operations]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: ADR-0001
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Shared territorial compute

## Requirements

### Process economy

Creating an agent identity or session MUST NOT create a dedicated database, Qdrant
collection, embedding model, reranking model, or consolidation LLM process.

### Capability routing

Workers MUST request capabilities through a model-gateway port using privacy,
quality, latency, and cost policy. Domain code MUST NOT select concrete model names.

### Deterministic-first behavior

Normalization, hashing, policy, idempotency, and deterministic ranking MUST run
without an LLM. LLM-dependent work MUST be batched where safe and remain visibly
pending or degraded when compute is unavailable.

### Isolation

Shared workers MUST preserve identity context and authorized content boundaries
through queue, model request, cache, and result publication.

Scenario: one hundred agent instances start. Worker pools may scale by capacity,
but model processes and storage topology do not scale one-for-one with identities.
