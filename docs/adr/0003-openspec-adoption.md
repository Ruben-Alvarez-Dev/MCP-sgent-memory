# ADR-0003 — OpenSpec adoption as the workflow backbone

- **Status**: accepted · **Date**: 2026-07-12 · **Deciders**: Rubén + dev-team
- **Context**: the 2026-07-12 audit found the repo's documentation and reality had diverged (aspirational README/ROADMAP claims, undeclared dependencies, code paths that lie about their own status) and that no gate stops this from recurring — no CI, no mandatory review of assumptions, no traceable link between "why we changed X" and the change itself (`docs/plan/IMPROVEMENT-PLAN.md` §1, §2). Rubén's standing norm is spec-driven development with approval gates before touching existing code.

## Decision

1. **Adopt [OpenSpec](https://github.com/Fission-AI/OpenSpec) conventions** as the operating model, per plan §3.1:

   ```
   openspec/
   ├── AGENTS.md          # binding verification protocol (gates, norms)
   ├── project.md         # tech stack, architecture, conventions, domain glossary
   ├── specs/             # THE TRUTH — current deployed capabilities, one folder per capability
   └── changes/           # PROPOSALS — active work; archived into specs/ on completion
       └── <change-id>/   # proposal.md (why/what), design.md (how), tasks.md (checklist), spec deltas
   ```

2. **`specs/` vs `changes/` split**: `specs/` is read-only during feature work — it only changes by archiving an approved change. Every Phase-plan item becomes one or more `changes/<id>/`. A change may not merge until its `tasks.md` is checked, its spec delta is written, and quality gates pass (plan §3.4). Bugfixes above P2 severity also go through a lightweight change proposal — that is what "100% spec-driven" means in this repo (no informal exception for "small" fixes beyond the one-time Phase 0 window recorded in ADR-0001).
3. **`openspec/AGENTS.md` is binding**, not advisory, and applies to every agent (orchestrator and subagents) in every session:
   - No mocks/stubs/fakes/demo data outside `tests/`; no claim of "working" without executable proof; unverifiable work is reported as **UNVERIFIED**, never as done.
   - Dual validation: every assumption needs two independent, named sources (e.g. reading code + executing it; docs + a live probe) before it is actionable.
   - Strict TDD with verbatim red→green evidence captured in `openspec/changes/<id>/evidence/I<NN>.md`.
   - Work advances only as numbered iterations `I01, I02, …` mapped 1:1 to `tasks.md`, each with a granular English commit referencing `[<change-id>/I<NN>]`.
4. Open-standards matrix layered on top (plan §3.2): OpenAPI 3.1 for the HTTP sidecar, JSON Schema 2020-12 for persisted data shapes, MADR 4.0 for `docs/adr/`, Conventional Commits 1.0, SemVer 2.0 (ADR-0002), Keep a Changelog 1.1, ruff/mypy, pytest/Vitest.

## Consequences

(+) Every non-trivial change carries its own why/what/how/checklist and evidence trail, closing the "documentation lies" failure mode the audit found. (+) The binding protocol makes "presenting unverified work as working" an explicit, named failure instead of an implicit risk. (+) `specs/` becomes queryable ground truth for "what does this system actually do right now", replacing README/ROADMAP in that role. (−) Process overhead on small fixes, mitigated by a lightweight bugfix proposal template (plan §2.3 risk register acknowledges this and accepts the tradeoff). (−) Requires discipline to keep `specs/` in sync via archival rather than direct edits — enforced by the AGENTS.md rule that `specs/` changes only through an approved, archived change.
- **Related**: ADR-0001 (source material for the initial `specs/` baseline), ADR-0007 (hexagonal architecture executed as OpenSpec changes with the strangler/boy-scout rule).
