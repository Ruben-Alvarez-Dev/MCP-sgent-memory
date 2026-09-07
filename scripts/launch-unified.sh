#!/bin/bash
# launch-unified.sh — strict-mode launcher for the unified MCP server (M4).
#
# Secrets policy: the agent token NEVER lives in files (mcp.json, .env).
# It is stored in the macOS Keychain under service "memory-zero/<agent_id>"
# and pulled here at boot. Fail-closed: no keychain entry → no server
# (strict boot would raise IdentityError anyway — this just fails earlier
# with a clear message).
#
# One-time setup:
#   scripts/register_agent.py register <agent_id>     # prints the token ONCE
#   security add-generic-password -s "memory-zero/<agent_id>" -a "$USER" -w '<token>'
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export MEMORY_SERVER_DIR="${MEMORY_SERVER_DIR:-$PROJECT_ROOT}"

AGENT_ID="${MEMORY_AGENT_ID:-}"
if [ -z "$AGENT_ID" ]; then
    echo "ERROR: MEMORY_AGENT_ID is required (strict launcher)" >&2
    exit 1
fi

TOKEN="$(security find-generic-password -s "memory-zero/${AGENT_ID}" -a "$USER" -w 2>/dev/null)" || {
    echo "ERROR: no Keychain entry 'memory-zero/${AGENT_ID}' — register with scripts/register_agent.py first" >&2
    exit 1
}
if [ -z "$TOKEN" ]; then
    echo "ERROR: Keychain entry 'memory-zero/${AGENT_ID}' is empty" >&2
    exit 1
fi

export MEMORY_AGENT_TOKEN="$TOKEN"
export MEMORY_IDENTITY_MODE="${MEMORY_IDENTITY_MODE:-strict}"

exec "$PROJECT_ROOT/.venv/bin/python3" -u "$PROJECT_ROOT/src/unified/server/main.py"
