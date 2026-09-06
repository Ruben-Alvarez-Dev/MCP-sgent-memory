#!/bin/bash
# generate-mcp-config.sh — Generate config/mcp.json from config/.env (single source of truth)
#
# Generates a client config identical in form to install/config.sh output:
#   command  = <INSTALL_DIR>/.venv/bin/python3
#   args     = -u <INSTALL_DIR>/src/unified/server/main.py   (absolute path)
#   env      = PYTHONPATH, MEMORY_SERVER_DIR + embedding vars from .env
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

# ── Optional identity (M4) — NOT written by default ───────────────────
# Identity keys (see config/.env.example) are appended to the generated
# env block ONLY if MEMORY_AGENT_ID and MEMORY_AGENT_TOKEN are explicitly
# set (exported, or uncommented in config/.env). By default they stay out
# of the generated file. To pin an identity by default, uncomment:
#
#   MEMORY_AGENT_ID=director-1
#   MEMORY_AGENT_TOKEN=<token-from-register_agent.py>
#   MEMORY_IDENTITY_MODE=strict
#
# in config/.env before running this script.
IDENTITY_BLOCK=""
if [ -n "${MEMORY_AGENT_ID:-}" ] && [ -n "${MEMORY_AGENT_TOKEN:-}" ]; then
    IDENTITY_BLOCK=',
        "MEMORY_AGENT_ID": "'"${MEMORY_AGENT_ID}"'",
        "MEMORY_AGENT_TOKEN": "'"${MEMORY_AGENT_TOKEN}"'",
        "MEMORY_IDENTITY_MODE": "'"${MEMORY_IDENTITY_MODE:-strict}"'"'
fi

TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_OUT"' EXIT

cat > "$TMP_OUT" << EOF
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "${PYTHON}",
      "args": ["-u", "${INSTALL_DIR}/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "${INSTALL_DIR}/src",
        "MEMORY_SERVER_DIR": "${INSTALL_DIR}",
        "EMBEDDING_BACKEND": "${EMBEDDING_BACKEND:-llama_server}",
        "LLAMA_SERVER_URL": "${LLAMA_SERVER_URL:-http://127.0.0.1:8081}",
        "EMBEDDING_MODEL": "${EMBEDDING_MODEL:-bge-m3}",
        "EMBEDDING_DIM": "${EMBEDDING_DIM:-1024}"${IDENTITY_BLOCK}
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
