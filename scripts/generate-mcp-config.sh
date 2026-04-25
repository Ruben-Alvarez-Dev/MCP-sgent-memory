#!/bin/bash
# generate-mcp-config.sh — Generate mcp.json from .env (single source of truth)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/config/.env"
OUTPUT="$PROJECT_ROOT/config/mcp.json"
PI_OUTPUT="$HOME/.pi/mcp.json"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
fi

# Source env
set -a; source "$ENV_FILE"; set +a

INSTALL_DIR="${PROJECT_ROOT}"
PYTHON="${INSTALL_DIR}/.venv/bin/python3"

cat > "$OUTPUT" << EOF
{
  "mcpServers": {
    "agent-memory": {
      "command": "${PYTHON}",
      "args": ["-m", "unified.server.main"],
      "cwd": "${INSTALL_DIR}/src",
      "env": {
        "QDRANT_URL": "${QDRANT_URL:-http://127.0.0.1:6333}",
        "EMBEDDING_BACKEND": "${EMBEDDING_BACKEND:-llama_server}",
        "EMBEDDING_DIM": "${EMBEDDING_DIM:-1024}",
        "EMBEDDING_MODEL": "${EMBEDDING_MODEL:-}",
        "LLAMA_SERVER_URL": "${LLAMA_SERVER_URL:-http://127.0.0.1:8081}",
        "LLM_BACKEND": "${LLM_BACKEND:-llama_cpp}",
        "LLM_MODEL": "${LLM_MODEL:-qwen2.5:7b}",
        "SERVER_DIR": "${INSTALL_DIR}",
        "DATA_DIR": "${INSTALL_DIR}/data",
        "VAULT_PATH": "${INSTALL_DIR}/vault",
        "ENGRAM_PATH": "${INSTALL_DIR}/data/memory/engram",
        "DREAM_PATH": "${INSTALL_DIR}/data/memory/dream",
        "THOUGHTS_PATH": "${INSTALL_DIR}/data/memory/thoughts"
      }
    }
  }
}
EOF

echo "✅ Generated $OUTPUT"

# Optionally copy to Pi config
if [ -d "$(dirname "$PI_OUTPUT")" ]; then
    cp "$OUTPUT" "$PI_OUTPUT"
    echo "✅ Copied to $PI_OUTPUT"
fi
