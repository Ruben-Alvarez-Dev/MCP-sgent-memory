# Delta spec: isolation (M1-lite)

## Purpose (existing capability — no Purpose change)

## MODIFIED Requirements

### Requirement: ISO-03 Reminders are scope-namespaced
The system SHALL store reminders under per-scope directories
(`<base>/<sha256(scope)[:16]>/`) and `check_reminders`/`dismiss_reminder` SHALL
read only the caller's scope directory plus the `shared` directory. The
`agent_id` parameter SHALL be validated by `normalize_scope` (reject empty,
reserved, traversal, glob, overlong). Legacy root-level `*.json` files SHALL be
migrated once into `shared/` on first access.

#### Scenario: A1 cross-agent reminder read
- GIVEN a reminder saved with `agent_id="agent-a"`
- WHEN `check_reminders(agent_id="agent-b")` runs
- THEN zero reminders are returned.
- WHEN `check_reminders(agent_id="agent-a")` runs
- THEN the reminder is returned.

#### Scenario: Shared visibility preserved
- GIVEN a reminder saved with `agent_id="shared"`
- WHEN any valid scope lists reminders
- THEN the shared reminder is returned.

### Requirement: ISO-04 Decisions retrieval is scope-namespaced
`_retrieve_L3_decisions` SHALL accept `agent_scope` and search only the shared
tree (excluding `_scopes/`) plus `_scopes/<scope>/`. `_retrieve_parallel` SHALL
forward its `agent_scope`. `save_decision`'s `scope` parameter (previously
decorative) SHALL select the write root: `shared` → `<root>/<category>/`,
otherwise `<root>/_scopes/<scope>/<category>/`, and persist `scope` in
frontmatter. `search_decisions`/`list_decisions` SHALL accept `agent_scope` and
apply the same roots (previously `list_decisions.scope` was ignored).

#### Scenario: A2 cross-agent decision search
- GIVEN a decision saved with `scope="agent-a"`
- WHEN retrieval runs with `agent_scope="agent-b"`
- THEN the decision is absent; with `agent_scope="agent-a"` it is present.
- WHEN retrieval runs with `agent_scope="agent-c"`
- THEN shared decisions are present and `agent-a` decisions are absent.

## ADDED Requirements

### Requirement: ISO-09 Canonical scope
The system SHALL validate every scope string with `shared.scope.normalize_scope`:
strip + lowercase, non-empty, max 32 chars, `^[a-z0-9][a-z0-9_-]{1,31}$`,
rejecting reserved names (`global`, `merged`, `consolidated`, `narrative`,
`dream`). Violations SHALL raise `ScopeError` (tools fail closed, no fallback
to global). `shared` is the legitimate public scope, not a bypass.

#### Scenario: Traversal rejected
- GIVEN scope `"../../etc"` (or `"*"`, `""`, `"a"x33`, `"global"`, `"a b"`)
- WHEN any namespaced operation runs
- THEN `ScopeError` is raised and nothing is read or written.

### Requirement: ISO-10 Namespace directories without traversal
Scope-derived filesystem paths SHALL NEVER embed raw scope text except through
`normalize_scope` output (regex-safe by construction, no `/`, no `..`), and
reminders SHALL use `sha256(scope)[:16]` directory names. A containment test
SHALL assert every resolved path stays under its jail root.

## Explicitly NOT changed (deferred with owner)
- ISO-05/ISO-01/ISO-06/ISO-07/ISO-08 → M2 (engine enforcement, jail FS, deprecate
  mixed scopes) and M4 (harness-asserted identity). Documented, not silently dropped.
