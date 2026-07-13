---
id: DESIGN-implement-identity-session-core
title: Identity and session core design
type: design
status: approved
version: 0.1.0
owners: [identity, memory, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Identity and session core design

## Problem

Identity, session state, authorization, and infrastructure are entangled in legacy
handlers. Caller-provided strings can become effective authority.

## Options

1. Patch each legacy handler independently.
2. Introduce pure domain/policy/application packages and later adapt handlers by
   strangler migration.
3. Begin with PostgreSQL/RLS and derive domain behavior from tables.

Option 2 is selected. Option 1 duplicates security rules; option 3 makes storage
shape the domain before invariants are executable.

## Components

```text
application/
  StartSession, AdvanceSession, EndSession, AuthorizeMemoryAccess
    -> ports/
       Clock, Uuid7Generator, SessionRepository
    -> policy/
       IsolationPolicy
    -> domain/
       IdentityContext, Session, MemoryOwner, scopes, states, failures
```

Dependency direction is `application -> policy/ports/domain`; `policy -> domain`;
`ports -> domain`; `domain -> standard library`.

## Identity invariants

- New identifiers are real `uuid.UUID` values with version 7 and RFC 4122 variant.
- All timestamps are timezone-aware UTC.
- `IdentityContext` is frozen and requires a non-empty purpose, capabilities,
  session, task, plaza, credential version, and policy version.
- Agent principals require user, agent definition, and agent instance identifiers.
- `assert_active(at)` rejects not-yet-issued, expired, and invalid intervals.

## Session invariants

- A session is immutable; transitions return a replaced value.
- Allowed transitions: `active -> ending -> ended`; `active|ending -> revoked`.
- Only active sessions accept sequence advancement.
- The domain accepts an expected high-watermark and returns the next sequence,
  rejecting stale concurrent writers.

## Isolation policy

The initial policy supports only `session_private` and `agent_private`:

- tenant must always match;
- session-private requires matching user, agent instance, session, and task;
- agent-private requires matching user and agent instance;
- requested scope must not exceed the verified scope ceiling;
- required capability must be present;
- unsupported broader scopes deny, even when identifiers match.

The policy returns an explicit decision value for permitted access and raises a
typed denial containing a non-sensitive reason code for denied access.

## Application transactions

Use cases depend on repository, clock, and UUID ports. The repository contract
uses optimistic version/high-watermark comparison. Test doubles remain inside
tests; a real PostgreSQL adapter is deferred.

## Trade-offs

- Immutable values allocate on transition but make races and audit reasoning clear.
- Supporting only two private scopes is deliberately incomplete but secure; broader
  behavior cannot accidentally become allowed.
- No adapter means no production claim yet, but the security kernel becomes
  executable before storage/protocol coupling.

## Acceptance criteria

- Pure import boundaries are mechanically verified.
- Deny matrix covers different tenant, user, agent instance, session, task,
  capability, ceiling, and unsupported scope.
- Session transition and optimistic concurrency cases are fully tested.
- Existing legacy core baseline is not worsened by the new isolated packages.
