#!/bin/bash
VAULT_DIR="$HOME/MCP-servers/MCP-agent-memory/data/Lx-persistent"
LOG_FILE="$VAULT_DIR/.system/watcher.log"
PYTHON="$HOME/MCP-servers/MCP-agent-memory/.venv/bin/python3"
PROCESSOR="$HOME/MCP-servers/MCP-agent-memory/bin/vault_processor.py"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Watcher triggered" >> "$LOG_FILE"
"$PYTHON" "$PROCESSOR" 2>&1 >> "$LOG_FILE"
