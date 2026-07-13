---
id: PROJECT-jart-memory
title: Jart Memory reconstruction
type: project
status: active
version: 0.1.0
owners: [memory]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: Jart-OS-governance
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Jart Memory reconstruction

## Objective

Reconstruct `MCP-agent-memory` into a lightweight-client, territorial memory
service that gives every user, agent instance, session, and task logically private
memory while sharing storage infrastructure and model compute safely.

## Current truth

The `main` branch is a legacy single-installation implementation. It is installable
but has one reproducible unit failure, unlocked dependencies, 251 all-tree Ruff
findings, and no verified multi-tenant authorization boundary. Existing pull
requests are preserved source lines, not approved integration bases.

No target capability described in the active foundation change is implemented or
deployed merely because its contract exists.

## Target boundaries

```text
lightweight clients and MCP adapters
  -> trusted identity/plaza gateway
    -> Jart Memory application and policy
      -> authoritative metadata, journal, and governed content
      -> derived indexes
      -> shared asynchronous compute workers
```

The core is protocol-agnostic. MCP, HTTP, PostgreSQL, Qdrant, NATS, object stores,
model gateways, and agent platforms are adapters.

## Canonical bounded contexts

- Identity Context: verified principal, plaza, hierarchy, purpose, and policy.
- Sessions: immutable ownership and monotonic event sequence.
- Memory: capture, versions, correction, retention, and authorized retrieval.
- Promotion: consequence-gated derivation into a broader scope.
- Storage Authority: transactional truth, append-only journal, and derived indexes.
- Inference: shared territorial compute through explicit ports and capability
  profiles; no model process per agent.
- Observability: T9 metrics/traces and UCO anomaly/control signals without default
  access to raw memory.

## Delivery order

1. Preserve and baseline every recoverable source line.
2. Ratify contracts and threat scenarios.
3. Introduce architecture and validation gates without behavior changes.
4. Implement identity and isolation vertically with deny-first TDD.
5. Separate clients, service lifecycle, storage, and shared compute.
6. Implement governed promotion and revocation.
7. Migrate real stores through idempotent dry runs and reconciliation.
8. Package and operate through Jart-UP, T9, and UCO.
