---
id: SPECDELTA-session-lifecycle-core
title: Session lifecycle implementation delta
type: spec
status: proposed
version: 0.1.0
owners: [identity, memory]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation, implement-identity-session-core]
---

# Session lifecycle implementation delta

## ADDED Requirements

### Immutable transitions

The Python domain MUST implement legal session transitions as immutable value
replacement and reject illegal transitions with a typed failure.

### Monotonic optimistic sequence

Advancing a session MUST require the caller's expected high-watermark. A mismatch
MUST reject without advancing.

Scenario: two writers expect sequence 4. The first obtains 5; the second receives
a stale-session failure and cannot also produce 5.
