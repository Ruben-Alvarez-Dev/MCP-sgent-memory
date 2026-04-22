#!/bin/bash
# config.sh — Configuration generation
set -euo pipefail
INSTALL_DIR="${1:?Usage: config.sh <install_dir>}"
QDRANT_PORT="${2:-6333}"

mkdir -p "$INSTALL_DIR/config" "$INSTALL_DIR/data"/{memory/{engram,dream,thoughts,heartbeats,reminders},staging_buffer} "$INSTALL_DIR/vault"

cat > "$INSTALL_DIR/config/.env" << EOF
QDRANT_URL=http://127.0.0.1:$QDRANT_PORT
EMBEDDING_BACKEND=llama_server
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
VAULT_PATH=$INSTALL_DIR/vault
ENGRAM_PATH=$INSTALL_DIR/data/memory/engram
DREAM_PATH=$INSTALL_DIR/data/memory/dream
THOUGHTS_PATH=$INSTALL_DIR/data/memory/thoughts
HEARTBEATS_PATH=$INSTALL_DIR/data/memory/heartbeats
REMINDERS_PATH=$INSTALL_DIR/data/memory/reminders
STAGING_BUFFER=$INSTALL_DIR/data/staging_buffer
AUTOMEM_JSONL=$INSTALL_DIR/data/raw_events.jsonl
MEMORY_SERVER_DIR=$INSTALL_DIR
EOF

cat > "$INSTALL_DIR/config/mcp.json" << EOF
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "$INSTALL_DIR/.venv/bin/python3",
      "args": ["-u", "$INSTALL_DIR/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:$QDRANT_PORT",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}
EOF
echo "  ✓ config/.env"
echo "  ✓ config/mcp.json"
