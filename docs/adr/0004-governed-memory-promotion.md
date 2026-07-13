---
id: ADR-0004
title: Governed derived-version promotion
type: adr
status: proposed
version: 0.1.0
owners: [memory, governance, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# ADR-0004: Governed derived-version promotion

## Context

Automatic shared search or in-place scope mutation can expose private memory
without evidence, review, lineage, or revocation semantics.

## Decision

Crossing from private to team/domain/tenant/global scope requires a promotion case.
Approval materializes a new derived version with provenance, redaction, policy, and
decision lineage. The original private version remains unchanged.

## Consequences

- Direct broad-scope writes are prohibited.
- Triumvirate and Guardian/HITL gates depend on consequence and sensitivity.
- Revocation withdraws the derived view without erasing authorized source evidence.
- Audit stores actor, policy, decision, and hashes, not raw memory.
