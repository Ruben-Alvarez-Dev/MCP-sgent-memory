# ADR-001 — Project Entity Metadata Convention

- Status: Accepted
- Date: 2026-06-07
- Deciders: Rubén Álvarez (owner), Claude (architect)

## Context and Problem Statement

The entity system (`src/shared/entity_registry.py`, SQLite at `data/entity_timeline.db`)
was designed as a "phone book": identity, kind, status, summary, timeline and relations,
with FTS5 indexes over names, summaries and events. The `metadata` column is a free-form
JSON TEXT field, but nothing in the original design specified what it should contain for
`kind="project"` entities. As a result, all 45 production entities carry `metadata: {}`.

Consequence observed in practice (2026-06-07 review): the catalog cannot answer
"where does project X live, which repo backs it, what is it for", so every working
session re-scans `~/Code` and `~/MCP-servers` from scratch instead of querying memory.

## Decision

Adopt a metadata convention for `kind="project"` entities. No schema migration is
required: the existing JSON column and FTS5 indexes already support it.

Required keys:

| Key | Type | Description |
|---|---|---|
| `local_path` | string | Absolute path of the working copy on the primary machine |
| `repo_url` | string \| null | Remote URL (`null` if no remote exists) |

Recommended keys:

| Key | Type | Description |
|---|---|---|
| `default_branch` | string | Usually `main` |
| `machine` | string | Host that owns the working copy (e.g. `mbp-m1-max`) |
| `origin` | string | `own` for first-party projects, `third-party` for clones |
| `last_audit` | string | ISO-8601 date of the last structured review, if any |

Rules:

1. Every first-party project under `~/Code` and `~/MCP-servers` gets exactly one
   `kind="project"` entity whose `name` matches the directory name.
2. Third-party clones are only registered when they play an active role in the
   stack, and must carry `origin: "third-party"`.
3. `summary` stays a one-paragraph human description (it is FTS-indexed); structured
   facts go in `metadata`, never prose.
4. Agents must query the entity catalog (`entity_search`, `entity_get_by_name`)
   before scanning the filesystem.

## Considered Options

- **Free-form metadata convention (chosen)** — zero migration, immediately usable,
  enforced by convention and review.
- **Dedicated columns (`repo_url`, `local_path`)** — stronger typing but requires a
  schema migration and code changes in registry, MCP layer and vault bridge for
  little gain at the current scale (~50 entities).
- **Repo entities + relations** — model each repository as its own entity linked by
  a `backed_by` relation. More expressive, but overkill until multi-repo projects
  appear; can be layered on top of this convention later without conflict.

## Consequences

- Positive: project discovery becomes a memory query; disk scans become the
  exception. Provenance (`origin`, `last_audit`) makes staleness visible.
- Negative: JSON keys are not enforced by the schema; consistency depends on the
  registration tooling and periodic review.
- Out of scope (future ADR if needed): indexing code content (per-file timeline
  events or a Qdrant collection for entities).
