---
name: ops-scheduling-and-resilience-hardening
description: Workflow command scaffold for ops-scheduling-and-resilience-hardening in MCP-agent-memory.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /ops-scheduling-and-resilience-hardening

Use this workflow when working on **ops-scheduling-and-resilience-hardening** in `MCP-agent-memory`.

## Goal

Adds or updates operational scripts and launchd plists to schedule backups, health checks, self-healing, or lifecycle tasks.

## Common Files

- `scripts/*.sh`
- `etc/launchd/*.plist`
- `src/shared/health.py`
- `docs/RUNBOOK.md`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create or update shell scripts in scripts/ (e.g., backup-data.sh, lifecycle.sh, reembed-pending.sh, run-backpack.sh, smoke.sh)
- Create or update launchd plist files in etc/launchd/
- Optionally update Python health check or related operational code (e.g., src/shared/health.py)
- Document the operational change (e.g., docs/RUNBOOK.md)

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.