#!/bin/bash
# generate-mcp-config.sh — Generate config/mcp.json from config/.env (single source of truth)
#
# Generates a client config identical in form to install/config.sh output:
#   command  = <INSTALL_DIR>/.venv/bin/python3
#   args     = -u <INSTALL_DIR>/src/unified/server/main.py   (absolute path)
#   env      = PYTHONPATH + MEMORY_SERVER_DIR
#
# M9 (E2E audit 2026-09-07): the embedding env block (EMBEDDING_BACKEND,
# LLAMA_SERVER_URL, EMBEDDING_MODEL, EMBEDDING_DIM) is GONE — the engine is
# FTS5-only and nothing reads those vars anymore.
#
# Strict identity WITHOUT secrets in files: if MEMORY_AGENT_ID is set in
# config/.env, the generated config points at scripts/launch-unified.sh,
# which pulls the agent token from the macOS Keychain (service
# "memory-zero/<agent_id>") at boot. The token never touches mcp.json.
#
# Usage:
#   scripts/generate-mcp-config.sh             # Write config/mcp.json only
#   scripts/generate-mcp-config.sh --install   # Also copy to ~/.pi/mcp.json
#   scripts/generate-mcp-config.sh --help
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/config/.env"
OUTPUT="$PROJECT_ROOT/config/mcp.json"
PI_OUTPUT="$HOME/.pi/mcp.json"

usage() {
    echo "Usage: $(basename "$0") [--install]"
    echo ""
    echo "  Generates config/mcp.json from config/.env."
    echo "  --install   Also copy the generated file to $PI_OUTPUT"
    echo "  --help      Show this help"
}

INSTALL=false
for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=true ;;
        --help|-h) usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi

# Source env
set -a; source "$ENV_FILE"; set +a

INSTALL_DIR="${PROJECT_ROOT}"
PYTHON="${INSTALL_DIR}/.venv/bin/python3"

# ── Optional strict identity (M4) — launcher-based, NO secrets in files ──
# If MEMORY_AGENT_ID is set (exported, or uncommented in config/.env), the
# generated config switches to the Keychain-backed launcher. The token is
# NEVER written here; it lives in the macOS Keychain under service
# "memory-zero/<agent_id>" and scripts/launch-unified.sh pulls it at boot.
#
# To pin a strict identity by default, set in config/.env:
#
#   MEMORY_AGENT_ID=pi-agent
#
# and register the credential once:
#   scripts/register_agent.py register pi-agent    # prints the token ONCE
#   security add-generic-password -s "memory-zero/pi-agent" -a "$USER" -w '<token>'
LAUNCHER="${INSTALL_DIR}/scripts/launch-unified.sh"
USE_LAUNCHER=false
IDENTITY_ENV=""
if [ -n "${MEMORY_AGENT_ID:-}" ]; then
    if [ ! -x "$LAUNCHER" ]; then
        echo "ERROR: MEMORY_AGENT_ID is set but $LAUNCHER is missing or not executable" >&2
        exit 1
    fi
    USE_LAUNCHER=true
    IDENTITY_ENV=",
        \"MEMORY_AGENT_ID\": \"${MEMORY_AGENT_ID}\",
        \"MEMORY_IDENTITY_MODE\": \"strict\""
fi

TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_OUT"' EXIT

if $USE_LAUNCHER; then
    COMMAND="$LAUNCHER"
    ARGS="[]"
else
    COMMAND="$PYTHON"
    ARGS="[\"-u\", \"${INSTALL_DIR}/src/unified/server/main.py\"]"
fi

cat > "$TMP_OUT" << EOF
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "${COMMAND}",
      "args": ${ARGS},
      "env": {
        "PYTHONPATH": "${INSTALL_DIR}/src",
        "MEMORY_SERVER_DIR": "${INSTALL_DIR}"${IDENTITY_ENV}
      }
    }
  }
}
EOF

# Validate before clobbering the live config
python3 -m json.tool "$TMP_OUT" > /dev/null 2>&1 || {
    echo "ERROR: generated JSON is invalid; keeping previous $OUTPUT" >&2
    exit 1
}

mv "$TMP_OUT" "$OUTPUT"
trap - EXIT
echo "✅ Generated $OUTPUT"

# Copy to Pi config ONLY on explicit --install
if $INSTALL; then
    mkdir -p "$(dirname "$PI_OUTPUT")"
    cp "$OUTPUT" "$PI_OUTPUT"
    echo "✅ Copied to $PI_OUTPUT"
fi
