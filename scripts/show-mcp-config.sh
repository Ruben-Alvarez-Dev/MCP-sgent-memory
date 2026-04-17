#!/bin/bash
# MCP Memory Server — Show client configuration for all supported agents
# Usage: ./show-mcp-config.sh [gateway_url]
# Example: ./show-mcp-config.sh http://192.168.1.100:3050/mcp

GATEWAY_URL="${1:-http://127.0.0.1:3050/mcp}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Client Configuration              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Gateway: $GATEWAY_URL"
echo "  Tools:   45 across 7 servers"
echo "  Transport: HTTP/SSE"
echo ""

cat << ENDCLAUDE
┌─── Claude Code ────────────────────────────────────────────┐
│ File: ~/.claude/mcp/memory.json                            │
│                                                            │
│ {                                                          │
│   "mcpServers": {                                          │
│     "memory": {                                            │
│       "url": "$GATEWAY_URL",                               │
│       "type": "http"                                       │
│     }                                                      │
│   }                                                        │
│ }                                                          │
└────────────────────────────────────────────────────────────┘
ENDCLAUDE

echo ""

cat << ENDOPENCODE
┌─── OpenCode ───────────────────────────────────────────────┐
│ File: ~/.config/opencode/opencode.json → seccion "mcp":    │
│                                                            │
│ {                                                          │
│   "mcp": {                                                 │
│     "memory": {                                            │
│       "enabled": true,                                     │
│       "type": "remote",                                    │
│       "url": "$GATEWAY_URL"                                │
│     }                                                      │
│   }                                                        │
│ }                                                          │
└────────────────────────────────────────────────────────────┘
ENDOPENCODE

echo ""

cat << ENDCURSOR
┌─── Cursor ──────────────────────────────────────────────────┐
│ File: <project>/.cursor/mcp.json                           │
│                                                            │
│ {                                                          │
│   "mcpServers": {                                          │
│     "memory": {                                            │
│       "url": "$GATEWAY_URL",                               │
│       "type": "http"                                       │
│     }                                                      │
│   }                                                        │
│ }                                                          │
└────────────────────────────────────────────────────────────┘
ENDCURSOR

echo ""

cat << ENDVSCODE
┌─── VS Code Copilot ─────────────────────────────────────────┐
│ File: <workspace>/.vscode/mcp.json                         │
│                                                            │
│ {                                                          │
│   "servers": {                                             │
│     "memory": {                                            │
│       "type": "http",                                      │
│       "url": "$GATEWAY_URL"                                │
│     }                                                      │
│   }                                                        │
│ }                                                          │
└────────────────────────────────────────────────────────────┘
ENDVSCODE

echo ""
echo "┌─── One-liner para copiar/pegar ────────────────────────────┐"
echo "│                                                            │"
echo "│ Claude Code:                                               │"
echo "│   mkdir -p ~/.claude/mcp && echo '{\"mcpServers\":{\"memory\":{\"url\":\"$GATEWAY_URL\",\"type\":\"http\"}}}' > ~/.claude/mcp/memory.json"
echo "│                                                            │"
echo "│ Cursor:                                                    │"
echo "│   echo '{\"mcpServers\":{\"memory\":{\"url\":\"$GATEWAY_URL\",\"type\":\"http\"}}}' > .cursor/mcp.json"
echo "│                                                            │"
echo "│ VS Code:                                                   │"
echo "│   echo '{\"servers\":{\"memory\":{\"type\":\"http\",\"url\":\"$GATEWAY_URL\"}}}' > .vscode/mcp.json"
echo "└────────────────────────────────────────────────────────────┘"
