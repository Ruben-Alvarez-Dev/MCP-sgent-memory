#!/bin/bash
# config.sh — Configuration generation
set -euo pipefail
INSTALL_DIR="${1:?Usage: config.sh <install_dir>}"

mkdir -p "$INSTALL_DIR/config" "$INSTALL_DIR/data"/{memory/{engram,dream,thoughts,heartbeats,reminders},staging_buffer} "$INSTALL_DIR/vault"

cat > "$INSTALL_DIR/config/.env" << EOF
VAULT_PATH=$INSTALL_DIR/vault
STAGING_BUFFER=$INSTALL_DIR/data/staging_buffer
# Migration: renamed from AUTOMEM_JSONL (legacy key still accepted as
# fallback by shared/env_loader.py).
MEMORY_EVENTS_JSONL=$INSTALL_DIR/data/raw_events.jsonl
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
        "MEMORY_SERVER_DIR": "$INSTALL_DIR"
      }
    }
  }
}
EOF
echo "  ✓ config/.env"
echo "  ✓ config/mcp.json"
