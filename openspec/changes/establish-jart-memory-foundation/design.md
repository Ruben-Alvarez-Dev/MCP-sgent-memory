---
id: DESIGN-establish-jart-memory-foundation
title: Jart Memory target foundation design
type: design
status: proposed
version: 0.1.0
owners: [memory, identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Jart Memory target foundation design

## Problem

The legacy system couples client protocol, memory behavior, stores, indexes, and
model lifecycle while trusting caller-controlled scope identifiers. It cannot
provide a verifiable multi-user boundary or scale agent instances without
duplicating expensive stateful capabilities.

## Options

1. Preserve one full backpack per agent.
2. Share one unscoped global backpack.
3. Build a territorial multi-tenant service behind verified identity and
   lightweight adapters.

Option 3 is selected. Options 1 and 2 fail the resource-efficiency and isolation
objectives respectively.

## Architectural decision

The backpack is logically independent but physically lightweight. Every agent
process carries only a client adapter and, where required, an encrypted offline
spool. A territorial service shares durable storage, indexes, queues, and inference
pools across identities while enforcing namespace and policy boundaries.

```text
Agent / user client
  -> MCP or SDK adapter
    -> Gateway/T1 verifies plaza and constructs signed IdentityContext
      -> application use case
        -> policy authorizes the effective namespace
          -> authoritative transaction + journal/outbox
            -> derived-index and shared-compute workers
```

## Dependency direction

```text
clients/adapters/runtime -> application/policy -> ports/domain
```

- Domain owns identifiers, scopes, lifecycle states, versions, and invariants.
- Policy owns authorization, visibility composition, retention, and promotion.
- Application owns use-case orchestration and transactions.
- Ports isolate clocks, UUID generation, authorization, stores, indexes, events,
  model inference, telemetry, and audit.
- Runtime owns validated configuration and the single composition root.

MCP and HTTP DTOs are mapped at inbound adapters and never enter the domain.

## Identity boundary

T1/Gateway verifies a plaza and constructs an immutable `IdentityContext`.
The memory service verifies its signature/audience or receives it over a trusted
service boundary. Payload identifiers may only narrow the effective context.

The vocabulary distinguishes:

- `principal_id`: authenticated user, agent, or service actor;
- `user_id`: accountable human/user identity where applicable;
- `agent_definition_id`: stable agent mold or definition;
- `agent_instance_id`: one runtime birth of that definition;
- `session_id`: one bounded interaction lifecycle;
- `task_id`: the approved unit of work within that session.

All new identifiers are UUIDv7. Agent memory operations require non-null session
and task identifiers. Missing claims, unknown scopes, invalid policy versions, or
revoked plazas are denied.

## Scope and visibility

Ordered scopes are:

```text
session_private
agent_private
team_private
domain_controlled
tenant_controlled
global_golden
external_rag
```

The order does not itself grant access. Search composes separate authorized views
from narrowest to broadest. There is no global collection searched first and no
post-query Python filter that attempts to remove unauthorized results.

## Session and time model

A session has immutable ownership and a lifecycle of `active -> ending -> ended`,
with `revoked` available from any non-terminal state. Every captured event carries
an idempotency key and a monotonic `session_seq`. Records preserve occurrence,
ingestion, creation, update, validity, supersession, and tombstone time separately.
Timestamps are UTC RFC 3339; UUID ordering never substitutes for time fields.

## Storage authority

- PostgreSQL is authoritative for sessions, metadata, versions, grants, policies,
  promotion cases, decisions, and outbox state. RLS and constraints provide a
  second enforcement boundary.
- Governed object storage holds large or raw encrypted content under retention and
  tenant/territory key policy.
- An append-only journal records ingestion and state transitions for replay.
- Qdrant is a reconstructible index. It applies mandatory server-side identity,
  scope, policy, and classification filters.
- SQLite/FTS5 is an edge/offline cache, never central multi-tenant authority.

Index state is explicit: `pending`, `indexed`, or `failed`. Embedding failure never
creates a zero vector or reports complete success.

## Promotion boundary

Promotion creates a new derived version in a broader scope and retains lineage to
the private source. It never changes the source version's scope.

```text
proposed -> validating -> pending_triumvirate
  -> pending_guardian when consequence requires it
  -> approved | rejected
  -> materialized
  -> revoked when the broader view must be withdrawn
```

Validation covers provenance, deduplication, classification, redaction, evidence,
freshness, and target-scope policy. Decisions are signed and hashed into the audit
trail without embedding raw memory content.

## Shared compute

Capture normalization and policy remain deterministic where possible. Embedding,
reranking, consolidation, verification, and redaction run in territorial worker
pools through NATS and a model-gateway port. Clients submit capability and privacy
hints, not concrete model names. A `compute_profile` avoids collision with Jart-OS
infrastructure tiers T0-T9.

Creating N agent identities must not create N model processes, N databases, or N
Qdrant collections. Scale is by worker capacity and trust zone.

## Observability and control

- T9 receives metrics, traces, queue state, latency, degradation, errors, and
  promotion rates.
- UCO receives drift, anomaly, cross-scope attempt, plaza failure, integrity, and
  control signals.
- Mission Control presents operator state; it is not an authority or store.
- General telemetry and audit hashes exclude raw memory, prompts, credentials, and
  unredacted user content.

Exceptional forensic access requires an explicit capability, purpose, duration,
decision, and audit record.

## Failure behavior

- Invalid identity or policy: deny without storage or inference.
- Authoritative commit succeeds but index fails: return truthful `pending/failed`
  state and enqueue bounded retry.
- NATS unavailable: commit outbox state and apply backpressure; do not lose the
  authoritative event.
- Model unavailable: deterministic paths continue; LLM-dependent work remains
  pending/degraded and visible.
- Revocation: remove access immediately in policy and transport while preserving
  authorized historical evidence.

## Migration and compatibility

Legacy IDs are preserved through aliases and provenance. Ownerless or ambiguous
material is quarantined, never mapped to shared scope. Legacy MCP tools remain a
temporary compatibility adapter over the new use cases; they do not retain legacy
authorization semantics.

## Trade-offs

- Centralized capabilities reduce resource duplication but require explicit
  availability, backpressure, offline, and disaster-recovery behavior.
- Strong identity and storage enforcement add implementation complexity but remove
  unsafe caller-selected authority.
- Contract-first work delays feature coding but prevents divergent stores and
  adapters from inventing incompatible identity semantics.
- Governed promotion is slower than automatic sharing but preserves consent,
  lineage, revocation, and consequence review.

## Acceptance criteria

- The proposed contracts express identity, session, isolation, authority,
  promotion, shared compute, and observability boundaries without claiming runtime
  implementation.
- Dependency direction is compatible with Clean/Hexagonal Architecture.
- Failure behavior is truthful and deny-by-default.
- Every persisted contract carries schema version, ownership, UUIDv7 identifiers,
  UTC timestamps, and explicit lifecycle state.
- Later implementations can be delivered as vertical use cases through small
  ports without importing legacy framework concerns into domain or policy.
