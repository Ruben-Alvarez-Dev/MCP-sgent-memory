---
id: TESTPLAN-implement-identity-session-core
title: Identity and session core test plan
type: test-plan
status: approved
version: 0.1.0
owners: [testing, identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Identity and session core test plan

## TDD order

1. UUIDv7 and UTC validation failures.
2. Immutable identity construction and active-window checks.
3. Legal and illegal session transitions.
4. Monotonic sequence and stale-writer rejection.
5. Deny-first N×N ownership matrix.
6. Application orchestration through deterministic test ports.

## Required denial cases

- Different tenant, user, agent instance, session, or task.
- Missing capability.
- Requested scope above context ceiling.
- Team/domain/tenant/global/external scope before grants exist.
- Expired or not-yet-active context.
- Ended or revoked session capture.
- Stale expected sequence/version.
- Unknown operation or malformed identifier.

## Gates

- Targeted unit tests after each Red/Green.
- `./tools/check-foundation.sh`.
- Ruff and format over `src/jart_memory` and new tests.
- Import-boundary test prohibiting framework, I/O, and adapter imports in domain and
  policy.
- Existing `tests/core` characterization run; the known legacy `top_k` failure must
  remain the only failure or the change stops.

## Test data

All identities and times are deterministic, labeled TEST-ONLY, and generated or
sanitized. No production memory, user identity, credential, endpoint, or store is
used.
