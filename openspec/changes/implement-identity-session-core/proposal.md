---
id: CHANGE-implement-identity-session-core
title: Implement identity and session core
type: change-proposal
status: approved
version: 0.1.0
owners: [identity, memory, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: approval-2026-07-13-memory-identity-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Implement identity and session core

## Problem

The legacy runtime accepts free-form identity and scope values, uses implicit
session identifiers, and has no framework-independent policy boundary. The target
contracts exist, but no executable domain behavior enforces them.

## Outcome

Implement one pure, framework-independent vertical slice that:

- validates immutable UUIDv7 identity context and UTC validity;
- models session lifecycle and monotonic sequence without I/O;
- denies cross-tenant, cross-user, cross-agent, and cross-session access;
- exposes application use cases through small clock, UUID, and repository ports.

## Scope

- New `src/jart_memory/domain`, `policy`, `ports`, and `application` packages.
- Typed domain values, states, decisions, and failures.
- Deny-first unit and property-oriented test matrices using sanitized TEST-ONLY
  fixtures.
- Characterization proving legacy runtime files remain unchanged.

## Non-scope

- No MCP or HTTP adapter.
- No PostgreSQL, RLS, Qdrant, NATS, object store, model, or migration.
- No replacement of legacy handlers.
- No production deployment or data access.

## Test plan

`test-plan.md` defines Red-Green-Refactor iterations for UUIDv7, context validity,
session transitions, idempotent sequencing, scope narrowing, N×N isolation, and
application port orchestration.

## Acceptance criteria

- Domain and policy import only Python standard-library modules and each other in
  the permitted dependency direction.
- Every new behavior has captured Red and Green evidence.
- Invalid identity and every unknown capability/scope path deny explicitly.
- Session transitions are immutable and illegal transitions raise typed failures.
- Payload claims cannot widen verified context.
- Targeted tests, contract tests, Ruff, format, and import-boundary checks pass.

## Risks and rollback

The principal risk is encoding an incomplete policy lattice too early. The slice
therefore implements only session-private and agent-private ownership decisions;
broader team/domain/tenant/global grants remain denied until their own change.

Rollback removes the new isolated packages and tests. No legacy behavior or stored
state is modified.
