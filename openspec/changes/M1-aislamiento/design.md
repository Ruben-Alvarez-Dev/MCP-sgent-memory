# Design: M1-lite

## New module: `src/shared/scope.py` (no deps, no I/O)
`ScopeError(ValueError)`; `normalize_scope()`; `scope_dir_hashed(base, scope)`
→ `<base>/<sha256[:16]>` (reminders, opaque OK); `scope_subdir(base, scope,
prefix="_scopes")` → `<base>/_scopes/<normalized>` (decisions, human-browsable;
regex-safe by construction); `visible_dirs_*` helpers (own + shared);
`iter_namespaced_files(root, scope, pattern)` skipping `_scopes` in the shared
walk. Full 5-level `c:/p:/a:/s:/u:` path lands in M2; lite validates ONE segment
(the only shape callers use today: `director-1`, `default`, `shared`).

## L5 reminders (`src/L5_routing/server/main.py`)
`_save_reminder(r, scope)`, `_get_reminders(agent_id)` (own+shared dirs only),
`push_reminder` validates via `normalize_scope`, `check_reminders` validates,
`dismiss_reminder(reminder_id, agent_id="shared")` (new optional param, searches
own+shared). `_migrate_legacy_once()`: root `*.json` → `shared/` dir, guarded by
module flag (idempotent; prod dir is empty today, so this is belt-and-braces).

## Decisions (`src/L3_decisions/server/main.py`, `src/shared/retrieval/__init__.py`)
`_files(scope)` roots per ISO-04; `save/search/list` wire the scope params;
`get_decision`/`delete_decision` unchanged (path-confinement = capability model,
ownership check deferred to M2 — recorded, not hidden).
`_retrieve_parallel` forwards `agent_scope` to `_retrieve_L3_decisions`.
Note: retrieval's `L3_DECISIONS_PATH` env default differs from Config's path
(pre-existing inconsistency, NOT touched in lite; unified in M2).

## Failure modes
- Invalid scope → `ScopeError`, tool errors, zero I/O. No fallback to shared.
- Legacy files → migrated to shared (visible to all, as they always were).
- `_scopes` dir missing → treated as empty (no error).
- Concurrent writers → one JSON per reminder_id; last-writer-wins preserved.

## Adversarial coverage (tests/adversarial/test__ISO03__scope_isolation.py, CI)
Green now: A1 (reminders), A2-analog (decisions), A4-shape (empty/invalid scope
rejected), A7-shape (traversal), A8-shape (reserved spoof), A9-shape (no global
glob). Pending with owner (documented in file header + GATE): A3/A5/A6/A10/A14/A15
(M2), A11/A12/A16 (M5). No red tests in CI — pending items are explicit TODOs,
not silent gaps.

## Open questions
None blocking. M2 owns: 5-level namespace, engine filters, FS jail, identity.
