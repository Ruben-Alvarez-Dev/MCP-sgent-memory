---
id: SPECDELTA-identity-context-core
title: Identity context implementation delta
type: spec
status: proposed
version: 0.1.0
owners: [identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation, implement-identity-session-core]
---

# Identity context implementation delta

## ADDED Requirements

### Executable immutable context

The Python domain MUST expose an immutable identity value satisfying
`SPEC-identity-context` UUIDv7, required-agent-field, UTC validity, capability,
purpose, plaza, session, and task requirements without importing a framework.

Scenario: construction receives a version-4 session UUID. Construction fails with
a typed domain validation error before any use case executes.

### Active-window enforcement

Every identity-dependent use case MUST validate issue and expiry time using an
injected UTC clock.

Scenario: the current time equals or exceeds expiry. Authorization is denied.
