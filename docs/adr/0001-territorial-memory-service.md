---
id: ADR-0001
title: Territorial memory service with lightweight clients
type: adr
status: proposed
version: 0.1.0
owners: [memory]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# ADR-0001: Territorial memory service with lightweight clients

## Context

Physical backpack independence repeats databases, indexes, inference runtimes, and
model memory for every agent. A global shared backpack removes isolation.

## Decision

Use one logically multi-tenant territorial service per trust zone. Agent processes
carry lightweight MCP/SDK adapters and optional encrypted offline spools. Shared
workers access models through a model-gateway port.

## Consequences

- Agent creation does not load model processes or create databases.
- Identity and policy become mandatory service boundaries.
- Network/service availability becomes an operational dependency, mitigated by an
  explicit edge-offline mode.
- The legacy server becomes a compatibility adapter during strangler migration.

## Rejected alternatives

- Complete server per agent: excessive state and model duplication.
- One unscoped shared process: unacceptable cross-principal leakage risk.
- Embed memory into every agent framework: couples the domain to client lifecycle.
