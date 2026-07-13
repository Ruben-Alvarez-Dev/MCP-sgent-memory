---
id: HANDOFF-jart-memory-identity-core-2026-07-13
title: Jart Memory identity-core implementation checkpoint
type: handoff
status: active
version: 1.0.0
owners: [memory, identity, security]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: approval-2026-07-13-memory-identity-core
supersedes: []
superseded_by: null
related_changes: [establish-jart-memory-foundation, implement-identity-session-core]
---

# Jart Memory identity-core implementation checkpoint

## Resume objective

Continue the approved identity/session vertical slice without reconstructing the
investigation or changing scope. The MCP is **not yet fully redesigned, optimized,
or production-ready**. The clean foundation, approved implementation specification,
and immutable identity context are complete; session lifecycle, isolation policy,
application use cases, final gates, independent review, and the stacked draft pull
request remain open.

## Authority boundary

The active approval is
`/Users/ruben/MCP-servers/.jart-governance/approval.json`, approval ID
`approval-2026-07-13-memory-identity-core`.

Authorized implementation scope:

- immutable identity context;
- UUIDv7 session lifecycle and monotonic sequence control;
- deny-by-default private memory isolation;
- framework-independent application use cases over small ports;
- targeted TDD, frozen gates, granular commits, pushes, and a stacked draft pull
  request.

Explicitly deferred or excluded:

- production stores and migrations;
- legacy runtime handler migration;
- model loading or model inference changes;
- deployment and production data;
- broader team, domain, tenant, global, or external-RAG grants;
- GitHub-hosted workflow changes;
- merges;
- configuration of any product other than ChatGPT/Codex.

## Repository and branch state

- Repository: `Ruben-Alvarez-Dev/MCP-agent-memory`
- Development worktree:
  `/Users/ruben/MCP-servers/_recovery/jart-memory-phase0/worktrees/foundation-publish`
- Active branch: `change/jart-memory-identity-core`
- Approved base: `change/jart-memory-foundation`
- Published foundation head:
  `f2a2b3e33cba40365b032adacc7f0f8ebfc8607a`
- Published specification commit:
  `8c9bd1996fe96e639200b954fff8a03725880d27`
- Published identity implementation commit:
  `f3374d6cd5d45d1c0961801ca46847e429274342`
- Foundation draft pull request:
  `https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/pull/4`
- Identity-core stacked pull request: not opened yet; it belongs to final task I06.

The similarly named local branch `change/jart-memory-foundation` in the main clone
contains an unpublished workflow experiment and diverges from its remote. It is not
the active branch and must not be reset, deleted, merged, or published without new
explicit approval.

## Completed work

### Preservation and baselines

Phase 0 preservation, Git bundles, NVMe recovery, baseline reports, hashes, and
manifests are under:

- `/Users/ruben/MCP-servers/_recovery/jart-memory-phase0/`
- `/Users/ruben/MCP-servers/_investigation/jart-os-system-audit/`

The measured legacy baseline has one known failure: the no-LLM fallback ignores
`top_k` and returns all inputs. This is pre-existing behavior, not a green test.

### Foundation

The published foundation provides architecture/governance, proposed contracts,
locked dependencies, a provider-neutral frozen gate, and immutable review evidence.
Run it with:

```bash
./tools/check-foundation.sh
```

### Identity/session specification

The active OpenSpec change is:

```text
openspec/changes/implement-identity-session-core/
```

It contains the approved proposal, design, iteration plan, test plan, identity,
session, and isolation deltas, plus genuine iteration evidence.

### Immutable identity context

Implemented in `src/jart_memory/domain/identity.py` with:

- frozen, slotted `IdentityContext`;
- RFC 4122 UUIDv7 validation for authority-bearing identifiers;
- timezone-aware UTC issuance and expiry;
- explicit `PrincipalKind` and `MemoryScope` enumerations;
- complete agent identity requirements;
- semantic schema and policy versions;
- positive credential version;
- normalized non-empty capabilities and purpose;
- typed construction failures and active-window denials.

The package is included explicitly through `pyproject.toml`.

## Verified evidence at checkpoint

Identity tests:

```text
uv run --frozen --extra dev pytest tests/unit/domain/test_identity.py -q
17 passed in 0.02s
```

Foundation gate:

```text
./tools/check-foundation.sh
6 passed
Ruff passed
Ruff format passed
dependency lock passed
```

Focused quality gates:

```text
uv run --frozen --extra dev ruff check \
  src/jart_memory tests/unit/domain/test_identity.py
All checks passed!

uv run --frozen --extra dev ruff format --check \
  src/jart_memory tests/unit/domain/test_identity.py
4 files already formatted

git diff --check
exit 0
```

Detailed Red/Green records:

- `openspec/changes/implement-identity-session-core/evidence/I01.md`
- `openspec/changes/implement-identity-session-core/evidence/I02.md`

## Architecture direction retained from the investigation

The memory capability is an independent backpack from the caller's perspective,
but expensive shared compute must not be instantiated inside every agent. Domain,
policy, and application layers remain model-free. Embedding, reranking,
consolidation, and optional inference belong behind shared service ports in later
approved slices, allowing per-identity isolation without per-agent LLM duplication.

Authority always derives from a verified immutable context, never caller-provided
scope strings. Private records remain isolated until a separately specified,
auditable, deny-by-default promotion decision validates movement toward controlled
or golden scopes. The UCO/observability, security control, promotion, storage, and
shared-compute designs remain architectural context, not implemented production
claims in this slice.

## Remaining ordered work

1. **I03 — Session domain:** write failing tests, then implement immutable
   `Session`, legal transitions, active-only sequence advancement, and stale-writer
   rejection.
2. **I04 — Isolation policy:** write the full deny matrix, then implement
   `MemoryOwner`, explicit permit decisions, typed non-sensitive denials, ceiling
   enforcement, and support only for `session_private` and `agent_private`.
3. **I05 — Application layer:** implement `StartSession`, `AdvanceSession`,
   `EndSession`, and `AuthorizeMemoryAccess` over `Clock`, `Uuid7Generator`, and
   `SessionRepository` ports. Test doubles stay labeled and confined to tests.
4. **I06 — Verification/publication:** add the identity-core frozen gate, run the
   existing `tests/core` characterization without worsening its one known failure,
   run independent review, commit and push every complete unit, and open a stacked
   draft pull request against `change/jart-memory-foundation`.

## Exact next action

Start I03 with `tests/unit/domain/test_session.py`. The first run must fail because
the session module does not exist. Implement only after recording that Red state.
Do not begin stores, adapters, legacy handler migration, model optimization, or
deployment in this change.

## Resume commands

```bash
cd /Users/ruben/MCP-servers/_recovery/jart-memory-phase0/worktrees/foundation-publish
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/change/jart-memory-identity-core
sed -n '1,240p' docs/handoffs/2026-07-13-identity-core-checkpoint.md
sed -n '1,220p' openspec/changes/implement-identity-session-core/tasks.md
./tools/check-foundation.sh
uv run --frozen --extra dev pytest tests/unit/domain/test_identity.py -q
```

Before continuing, both revisions must match and the worktree must contain no
unrelated changes.
