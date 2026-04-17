#!/bin/bash
set -e

# Resolve directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MEMORY_SERVER_DIR="${MEMORY_SERVER_DIR:-$SCRIPT_DIR}"

# Start embedding server (daemon, ~72x faster than subprocess)
"$MEMORY_SERVER_DIR/scripts/start-embedding-server.sh"
export EMBEDDING_BACKEND=llama_server

# Start 1MCP Gateway
export ONE_MCP_CONFIG="${ONE_MCP_CONFIG:-$HOME/.config/1mcp/mcp.json}"
cd "${ONE_MCP_AGENT_DIR:-$HOME/Code/PROJECT-Memory/project_MEMORY-after-A0/1mcp-agent}"
exec node build/index.js serve --port 3050 --enable-config-reload false
