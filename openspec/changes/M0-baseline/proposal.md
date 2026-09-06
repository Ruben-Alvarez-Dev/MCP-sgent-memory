# Proposal: M0 — Baseline freeze + OpenSpec scaffold

## Intent
Freeze measurable truth about the current system BEFORE any migration work, and
stand up the OpenSpec machinery (config, base specs, test skeleton, traceability)
used by missions M1–M6. A migration without a baseline cannot prove parity or
no-regression; this mission exists so every later gate has something to compare
against.

## Scope
IN: `openspec/` scaffold; base specs for retrieval/isolation/consolidation/storage;
`tests/{unit,contract,integration,adversarial,eval,e2e}/` skeleton + pytest markers;
baseline evidence (suite status, latency probes, leak inventory, known bugs);
eval-40 query list definition (corpus fixture comes in M3 — current Qdrant holds
only 2 points, so recall-over-empty is recorded as degenerate, honestly).
OUT: any behavior change (hence `skip_specs: true`); any storage/retrieval edit;
any hook or harness work.

## Approach
1. Scaffold `openspec/` per spec-driven schema (done for config + 4 base specs).
2. Run `tests/core` + scope tests, record pass/fail + durations.
3. Probe live services (Qdrant :6333, embeddings :8091, backlog :8081) for latency.
4. Re-run leak inventory against code (L-R1, L-D1, L-F1, L-C1, L-V1) and file as
   confirmed findings in `evidence/`.
5. Author eval-40 list (queries + intents + languages) without relevance judgments
   (judgments land in M3 against the frozen fixture corpus).
6. Close GATE_0 (GO only if evidence is complete and committed).

## Capabilities
None (measurement only). `skip_specs: true`.

## Rollback plan
Delete `openspec/` and `tests/` skeleton; zero production impact (no code touched).

## Isolation impact
None (read-only probes). Leak inventory is documentation, not enforcement.
