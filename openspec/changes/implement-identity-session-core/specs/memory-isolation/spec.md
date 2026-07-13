---
id: SPECDELTA-memory-isolation-core
title: Memory isolation implementation delta
type: spec
status: proposed
version: 0.1.0
owners: [memory, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation, implement-identity-session-core]
---

# Memory isolation implementation delta

## ADDED Requirements

### Private-scope authorization kernel

The Python policy MUST authorize only session-private and agent-private ownership
in this change. Every broader or unknown scope MUST deny.

### Non-disclosing denial

Denied decisions MUST expose a stable reason code without returning target owner
content or confirming resource existence.

Scenario: principal A supplies principal B's memory owner tuple. Policy returns a
typed denial regardless of whether that resource exists.
