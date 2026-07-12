# Contributing

This project is 100% spec-driven and operates under a binding verification
protocol. Read `openspec/AGENTS.md` before touching any code — it overrides
convenience and applies to every contributor, human or AI agent.

## Spec-driven workflow (OpenSpec)

- No code lands without an approved proposal under `openspec/changes/<id>/`
  (bugfixes above trivial hygiene use a lightweight proposal).
- `openspec/specs/` is the current truth; it only changes by archiving a
  completed change.
- Work advances as numbered iterations `I01, I02, …` mapped 1:1 to a change's
  `tasks.md`. Each iteration needs: failing test (red) → minimal implementation
  (green) → `ruff check` clean → assumptions dual-validated against two
  independent sources → evidence file at
  `openspec/changes/<id>/evidence/I<NN>.md` (verbatim commands + output) →
  granular commit referencing `[<change-id>/I<NN>]` → `tasks.md` box ticked.
- Nothing simulated (mocks, stubs, fakes, canned data, placeholder
  implementations) is allowed outside `tests/`. If something can't be proven
  working, report it as **UNVERIFIED** — never as done.

Full protocol: `openspec/AGENTS.md`. Context and phased plan:
`docs/plan/IMPROVEMENT-PLAN.md`, `docs/plan/SESSION-HANDOFF.md`.

## Branch workflow

- The active integration branch is `change/phase0-foundation`. `main` only
  moves when Rubén explicitly approves a merge — never push to `main`
  directly.
- New work branches as `change/<openspec-id>` off `change/phase0-foundation`
  (or off `main` once a change is fully merged there), matching its
  `openspec/changes/<openspec-id>/` proposal, and merges back the same way.
- One topic per branch; keep branches short-lived.

## Commits

- [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/),
  in English, one logical change per commit (granular, not squashed).
- Type prefixes in use: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`,
  `ci`, `perf`. Use a scope when it clarifies the area, e.g.
  `fix(bootstrap): ...`, `feat(tier): ...`.
- Reference the iteration when applicable: `fix(embedding): ... [fix-embedding-truncation/I02]`.
- Commit messages are linted against Conventional Commits — see
  `commitlint.config.js`.
- Never commit with red tests. Never force-push or skip hooks without
  explicit approval from Rubén.

## Tests

```bash
# Core suite — no external services required
PYTHONPATH=src .venv/bin/python -m pytest tests/core -q

# App suite — needs Qdrant + an embedding backend; skips silently otherwise
PYTHONPATH=src .venv/bin/python -m pytest tests/app -q
```

TDD is mandatory: write the failing test first, capture the red run, then
implement the minimum to pass and capture the green run. Both go verbatim
into the iteration's evidence file.

## Lint & format

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

`ruff` config lives in `pyproject.toml` (`[tool.ruff]`, target `py312`,
line-length 120). Fix formatting with `.venv/bin/ruff format src tests`
before committing — CI and the pre-push hook both run the check-only form.

## Pre-commit hooks

A `.pre-commit-config.yaml` is provided (ruff check + format, on push). Install
it once per clone:

```bash
.venv/bin/pip install pre-commit   # dev extra, if not already present
.venv/bin/pre-commit install --hook-type pre-push
```

## Architecture rules

- Hexagonal ports & adapters, SOLID, DRY (ADR-0007). The domain never depends
  on infrastructure; all I/O sits behind a port.
- No cross-imports between `Lx_*` modules. No duplication — extract shared
  logic instead of copying it.
- No new dependency in `pyproject.toml` without an ADR.
- Model/backend selection is never hardcoded — it flows through
  `shared/model_tier.py` (see ADR-0004/0006).

## Docs & ADRs

- Docs are English; the vault's Spanish (ES) tree is the only user-facing
  exception.
- Architecture decisions are recorded as immutable ADRs in `docs/adr/`
  (MADR 4.0 style) — superseded, never edited.
