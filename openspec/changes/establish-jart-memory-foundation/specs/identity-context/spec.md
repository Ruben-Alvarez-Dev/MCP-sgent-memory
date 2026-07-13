---
id: SPEC-identity-context
title: Verified identity context
type: spec
status: proposed
version: 0.1.0
owners: [identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: ADR-0002
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Verified identity context

## Requirements

### Identity source

The service MUST derive effective identity from a verified immutable
`IdentityContext`. Request payloads MUST NOT widen tenant, principal, user, agent,
session, task, scope, capability, purpose, plaza, or policy claims.

Scenario: a payload names another tenant while the verified context names tenant A.
The request is denied before storage, retrieval, indexing, publication, or model
inference.

### Explicit runtime identity

Agent memory operations MUST carry distinct UUIDv7 values for agent definition,
agent instance, session, and task. Session and task MUST be present.

Scenario: two instances of the same agent definition run concurrently. Their
private events remain distinguishable by `agent_instance_id` and `session_id`.

### Deny by default

Missing, expired, revoked, wrong-audience, unknown-scope, or stale-policy context
MUST deny. No failure path MAY substitute shared/default/current authority.

### Temporal binding

The context MUST carry issue and expiry time in UTC RFC 3339 plus credential and
policy versions. The service MUST evaluate them at the use-case boundary.
