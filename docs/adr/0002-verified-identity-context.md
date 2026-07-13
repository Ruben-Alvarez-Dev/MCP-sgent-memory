---
id: ADR-0002
title: Verified immutable identity context
type: adr
status: proposed
version: 0.1.0
owners: [identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# ADR-0002: Verified immutable identity context

## Context

Legacy handlers accept caller-provided scope identifiers. This enables IDOR,
confused-deputy behavior, and accidental cross-session retrieval.

## Decision

T1/Gateway verifies the plaza and constructs a signed immutable `IdentityContext`.
The memory service derives effective authority from that context. Request payloads
may narrow, never widen, its claims. UUIDv7 identifies new principals, agent
instances, sessions, tasks, events, memories, and decisions.

## Consequences

- Missing, expired, revoked, unknown, or stale identity/policy denies by default.
- Agent definition and runtime instance are distinct identifiers.
- Identity issuance and authentication remain outside the cognitive memory core.
- PostgreSQL RLS provides a second boundary in addition to application policy.
