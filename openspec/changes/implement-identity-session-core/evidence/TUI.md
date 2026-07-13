---
id: EVIDENCE-implement-identity-session-core-tui
title: Local MVP terminal UI evidence
type: evidence
status: verified
version: 0.1.0
owners: [memory, testing]
deciders: [ruben]
created_at: 2026-07-13
last_verified_at: 2026-07-13
authority: CHANGE-implement-identity-session-core
supersedes: []
superseded_by: null
related_changes: [implement-identity-session-core]
---

# Local MVP TUI

Command:

```text
printf 'a\\ne\\n' | uv run --frozen --extra dev python -m jart_memory.tui
```

Observed states: `active` sequence `0`, `active` sequence `1`, then `ended`
sequence `1`. Ruff, format, and `git diff --check` passed. The TUI uses only
process-local memory and generated TEST-ONLY-style identifiers; it is not a
production adapter or legacy-handler integration.
