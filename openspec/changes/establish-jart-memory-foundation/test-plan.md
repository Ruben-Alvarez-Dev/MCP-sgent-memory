---
id: TESTPLAN-establish-jart-memory-foundation
title: Jart Memory foundation test plan
type: test-plan
status: approved
version: 0.1.0
owners: [testing, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Jart Memory foundation test plan

## Foundation gates

1. Parse every contract and normative document.
2. Validate every JSON Schema against Draft 2020-12.
3. Resolve every local schema reference from a closed registry.
4. Validate labeled sanitized fixtures for each record type.
5. Reject UUIDs that are not version 7, timestamps that are not UTC, unknown
   properties, missing ownership, implicit scope defaults, and incomplete states.
6. Prove the validation environment from a committed lock.

These gates validate contracts, not runtime authorization.

## Required implementation gates

### Identity and policy

- Payload tenant/user/agent/session/task values cannot widen verified claims.
- Missing or revoked plaza, expired context, wrong audience, and stale policy deny.
- Knowing another memory, version, event, thread, or promotion UUID grants nothing.

### N×N isolation matrix

For distinct tenants, users, agent definitions, agent instances, sessions, and
tasks, principal A cannot search, get, list, update, correct, tombstone, delete,
promote, infer existence, or overwrite principal B's material.

Run the matrix against:

- domain/policy units;
- application use cases;
- real PostgreSQL RLS;
- real Qdrant server-side filters;
- HTTP/MCP adapters;
- NATS consumers and replay paths;
- backup/restore and offline synchronization.

### Lifecycle and idempotency

- Session sequence is monotonic under concurrency.
- Replayed idempotency keys do not duplicate events, records, or promotions.
- Ended or revoked sessions cannot capture new events.
- Correct/supersede/tombstone preserves lineage and immutable evidence.

### Promotion

- Direct broad-scope writes are impossible through API, database, index, and bus.
- Missing evidence, policy, Triumvirate, or Guardian decision blocks materialization.
- Revocation removes only the derived broader view and preserves authorized source
  evidence.

### Storage and failure

- Authoritative commit plus index failure reports `pending/failed`, never success.
- Qdrant can be rebuilt from authority and journal with hash reconciliation.
- Model/dimension/normalization changes invalidate embedding cache correctly.
- Ownerless legacy records are quarantined.

### Privacy and observability

- T9, UCO, logs, traces, metrics, and audit hashes contain no raw memory by default.
- Exceptional forensic access expires and is independently audited.

## Test data

Only labeled deterministic fixtures, property-generated identities, and sanitized
snapshots may be used. Production memory and credentials are prohibited. Real
ephemeral components remain mandatory before release evidence.
