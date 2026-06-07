---
name: feature-implementation-across-module
description: Workflow command scaffold for feature-implementation-across-module in MCP-agent-memory.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /feature-implementation-across-module

Use this workflow when working on **feature-implementation-across-module** in `MCP-agent-memory`.

## Goal

Implements a new feature or capability, often touching both the main implementation and related shared modules or scripts.

## Common Files

- `src/L0_capture/server/main.py`
- `src/L0_to_L4_consolidation/server/main.py`
- `src/shared/embedding.py`
- `src/shared/llm/config.py`
- `src/shared/models/__init__.py`
- `src/shared/qdrant_client.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit or create main implementation file(s) in a module directory (e.g., src/L0_capture/server/main.py, src/L0_to_L4_consolidation/server/main.py, src/shared/embedding.py, src/shared/llm/config.py)
- Update or create related shared files (e.g., src/shared/models/__init__.py, src/shared/qdrant_client.py)
- Optionally add or update scripts or configuration (e.g., scripts/lifecycle.sh, etc/launchd/*.plist)
- Document or verify the change as needed

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.