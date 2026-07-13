# OpenSpec protocol

## Document states

- `openspec/specs/` describes verified deployed behavior only.
- `openspec/changes/` contains approved or proposed future behavior.
- A target contract must not be copied into current specs until implementation and
  all required gates pass.
- Evidence is immutable. Corrections create a linked evidence record.

## Required change package

Every change contains:

```text
proposal.md
design.md
tasks.md
test-plan.md
specs/<capability>/spec.md
evidence/I<NN>.md
```

Each requirement uses normative `MUST`, `MUST NOT`, `SHOULD`, or `MAY` language
and at least one observable scenario. Every task maps to a requirement, a gate,
and an evidence file.

## Iteration protocol

1. Orient against current source, authority, approval, and previous evidence.
2. Confirm the task is the smallest approved verifiable unit.
3. Capture Red evidence for the missing or incorrect behavior.
4. Implement the minimum Green behavior.
5. Refactor without changing the contract.
6. Run targeted, full applicable, contract, security, and static gates.
7. Record exact commands, exit codes, versions, hashes, and limitations.
8. Review scope and consequences, capture learning, and select the next task.

No iteration is complete while a required gate is red. Baseline failures remain
explicitly baseline failures; they are never relabeled as success.

## Security changes

Identity, authorization, isolation, promotion, destructive migration, retention,
and audit changes require:

- deny-first scenarios;
- an N×N cross-principal matrix;
- payload-widening, IDOR, replay, revocation, and concurrency cases;
- application-policy and real-storage enforcement evidence;
- independent review before acceptance.
