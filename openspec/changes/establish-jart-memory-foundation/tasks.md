---
id: PLAN-establish-jart-memory-foundation
title: Foundation iteration plan
type: plan
status: active
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

# Foundation iteration plan

- [x] I01 — Preserve GitHub and NVMe source lines with hashes and restoration
  evidence. Gate: forensic completeness.
- [x] I02 — Measure clean baselines for `main`, PR #1, and PR #3. Gate: executable
  test/static evidence with limitations.
- [x] I03 — Add target ADRs and the architecture change package. Gate: document structure,
  links, status, and scope review.
- [x] I04 — Add proposed capability specs and JSON Schema contracts through Red →
  Green validation. Gate: schema meta-validation, valid sanitized fixtures, and
  invalid deny-oriented fixtures.
- [x] I05 — Add a frozen foundation validation entrypoint. Gate:
  clean-environment reproduction from the committed lock.
- [x] I06 — Independent review, granular commits, push, and draft pull request.
  Gate: clean diff, no behavior changes, checks reported truthfully.

Behavior implementation, data migration, and deployment are explicitly deferred to
separate approved changes.
