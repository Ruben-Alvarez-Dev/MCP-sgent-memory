---
id: THREAT-memory-foundation
title: Jart Memory foundation threat model
type: security
status: proposed
version: 0.1.0
owners: [security, identity, memory]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-establish-jart-memory-foundation
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation]
---

# Jart Memory foundation threat model

## Assets

- identity/plaza claims and authorization policy;
- raw events, memory content, versions, lineage, and decisions;
- sessions, tasks, grants, promotion cases, and audit evidence;
- encryption keys, model inputs, embeddings, indexes, backups, and offline spools.

## Trust boundaries

1. Client/agent to Gateway/T1.
2. Gateway/T1 to Memory API.
3. Application/policy to authoritative stores.
4. Authority/outbox to NATS workers.
5. Workers to model gateway and derived indexes.
6. Runtime to T9, UCO, audit, backup, and restore systems.

## Priority threats and required controls

| Threat | Control | Required evidence |
|---|---|---|
| IDOR by known UUID | authorization on every read/write and RLS | N×N API plus storage tests |
| Payload scope widening | immutable verified context and intersection-only narrowing | deny-first policy tests |
| Cross-tenant vector leakage | mandatory server-side filters and trust-zone separation | real Qdrant adversarial tests |
| Confused deputy | audience, purpose, capability, and policy-version binding | token/context misuse tests |
| Replay/duplication | idempotency keys, session sequence, transactional outbox | concurrent replay tests |
| Revoked plaza reuse | immediate policy and transport revocation | active-session revocation test |
| Prompt/data exfiltration | classification, minimization, redaction, model-gateway policy | egress and log inspection |
| Malicious memory injection | provenance, content classification, quarantine, promotion gates | adversarial ingestion tests |
| Backup/offline leakage | encryption, per-tenant keys, retention, verified deletion | restore and key-isolation drill |
| Index-authority divergence | explicit index state and rebuild reconciliation | failure injection plus hash reconciliation |
| Promotion bypass | no direct broad writes in API/DB/bus | multi-path security tests |
| UCO/T9 overreach | content-free default telemetry and exceptional capabilities | trace/log/audit inspection |

## Security invariants

- Deny is the default result of missing or ambiguous authority.
- A UUID is an identifier, never a capability.
- Every persistent record has explicit owner, scope, version, and policy lineage.
- No automated retrieval or model decision can promote private memory.
- No fallback may silently weaken identity, encryption, filtering, or audit.

## Residual risks before implementation

Plaza token format, signature verification boundary, PostgreSQL RLS expressions,
tenant key management, NATS subject authorization, model-gateway privacy controls,
and forensic-access governance remain proposed and require separate accepted ADRs
and real-component tests.
