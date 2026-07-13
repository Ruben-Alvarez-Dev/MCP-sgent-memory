---
id: CHANGE-establish-jart-memory-foundation
title: Establish the Jart Memory contract foundation
type: change-proposal
status: approved
version: 0.1.0
owners: [memory, identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: approval-2026-07-13-memory-rebuild-phase-0-1
supersedes: []
superseded_by: null
related_changes: []
---

# Establish the Jart Memory contract foundation

## Problem evidence

The legacy server accepts caller-controlled user, agent, session, and scope values
without a complete authenticated multi-tenant policy boundary. It combines MCP,
storage, retrieval, consolidation, model lifecycle, and host assumptions. Deploying
it once per agent would replicate databases and up to three model roles per agent.

Forensic baselines at commits `c16c2c0`, `c40e45a`, and `7fe3433` show that no
existing branch is a safe complete base. PR #3 contains the strongest architectural
material but its mandatory coverage, lint, format, and integration gates are not
currently green.

## Desired outcome

Create a reviewable, implementation-neutral contract foundation for:

- trusted identity context;
- explicit session lifecycle;
- deny-by-default memory isolation;
- authoritative storage and reconstructible indexes;
- consequence-gated promotion;
- shared territorial inference and observability boundaries.

## Scope

- Repository governance and OpenSpec lifecycle.
- Proposed ADRs, capability specifications, and threat model.
- JSON Schema 2020-12 contracts for identity, session, event, memory, grant, and
  promotion records.
- Contract-validation tests and a deterministic CI gate.
- Recorded baselines and unresolved risks in the draft pull request.

## Non-scope

- No runtime behavior change.
- No merge or cherry-pick from PR #1 or PR #3.
- No database, Qdrant, NATS, model, or production deployment.
- No production data access or migration.
- No claim that proposed target contracts describe deployed behavior.

## Alternatives considered

1. Merge PR #3 wholesale: rejected because it combines 39 commits and 83 files and
   has red mandatory gates.
2. Extend the per-agent backpack: rejected because physical independence repeats
   stateful infrastructure and inference processes.
3. Share one global namespace: rejected because it cannot provide user/agent/session
   isolation or governed promotion.
4. Contract-first territorial service with lightweight clients: selected because
   it preserves logical independence while centralizing expensive capabilities.

## Acceptance criteria

- Every target requirement is explicitly proposed, not mislabeled as current.
- Schemas use UUIDv7, UTC RFC 3339 timestamps, explicit ownership, schema versions,
  and no implicit shared/default/current authority.
- Isolation and promotion deny cases are defined before implementation.
- Storage authority and derived-index behavior are unambiguous.
- T9 and UCO responsibilities are distinct and raw content is private by default.
- Contract validation is reproducible from a committed dependency lock.
- No existing core behavior changes in this foundation change.

## Test plan

The binding verification strategy is defined in `test-plan.md`. This foundation
change executes schema, reference, fixture, document, and reproducibility gates.
Runtime identity, N×N isolation, real PostgreSQL/Qdrant/NATS enforcement,
promotion, failure, migration, and privacy scenarios remain mandatory gates for
their later behavior changes and cannot be satisfied by schema tests alone.

## Risks

- Over-specification before adapter discovery: mitigate through small ports and
  proposed ADR status.
- False confidence from schema-only validation: mitigate by keeping behavior specs
  proposed and requiring real-component security gates later.
- Legacy identifier incompatibility: preserve aliases and provenance; never rewrite
  source identifiers silently.

## Rollback

The change is documentation, contracts, tests, and CI only. Rollback removes the
foundation commits; it does not alter runtime state or stored memory.
