#!/bin/bash
# configure.sh — Generate portable mcp.json and launchd plists
#
# Resolves ALL paths from a single variable: MEMORY_SERVER_DIR.
# Each server's env_loader.py derives data paths at runtime.
#
# Usage:
#   ./configure.sh                          # Auto-detect from script location
#   ./configure.sh /path/to/install/dir     # Explicit path
#   ./configure.sh --dry-run                # Show what would change
#   ./configure.sh --show                   # Show current config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Defaults (all derivable from MEMORY_SERVER_DIR) ────────────────

DIR="${1:-$PROJECT_ROOT}"
DRY_RUN=false
SHOW=false

case "$DIR" in
    --dry-run) DRY_RUN=true; DIR="$PROJECT_ROOT" ;;
    --show|-s) SHOW=true; DIR="$PROJECT_ROOT" ;;
esac

# Resolve to absolute path
DIR="$(cd "$DIR" && pwd)"

# Configurable with sane defaults
# Auto-detect free ports — increment if occupied
find_free_port() {
    local start_port="$1"
    local port="$start_port"
    local max="$((start_port + 100))"
    while [ "$port" -le "$max" ]; do
        if ! lsof -iTCP:"$port" -sTCP:LISTEN > /dev/null 2>&1; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
    done
    echo "$start_port"
    return 1
}

QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:$(find_free_port 6333)}"
LLAMA_SERVER_URL="${LLAMA_SERVER_URL:-http://127.0.0.1:$(find_free_port 8081)}"
GATEWAY_PORT="${GATEWAY_PORT:-$(find_free_port 3050)}"
LLM_BACKEND="${LLM_BACKEND:-ollama}"
LLM_MODEL="${LLM_MODEL:-qwen2.5:7b}"

MCP_CONFIG="${ONE_MCP_CONFIG:-$HOME/.config/1mcp/mcp.json}"
TEMPLATE="$PROJECT_ROOT/config/mcp.json.template"

# Colors
G="\033[32m" R="\033[31m" Y="\033[33m" B="\033[1m" X="\033[0m"

# ── Show mode ──────────────────────────────────────────────────────

if $SHOW; then
    echo "${B}Current Configuration${X}"
    echo "  MEMORY_SERVER_DIR: $DIR"
    echo "  QDRANT_URL:        $QDRANT_URL"
    echo "  LLAMA_SERVER_URL:  $LLAMA_SERVER_URL"
    echo "  LLM_BACKEND:       $LLM_BACKEND"
    echo "  LLM_MODEL:         $LLM_MODEL"
    echo "  MCP config:        $MCP_CONFIG"
    echo ""
    echo "Derived paths (handled by env_loader.py at runtime):"
    echo "  Data:         $DIR/data"
    echo "  Engram:       $DIR/data/memory/engram"
    echo "  Thoughts:     $DIR/data/memory/thoughts"
    echo "  Events JSONL: $DIR/data/raw_events.jsonl"
    echo "  Staging:      $DIR/data/staging_buffer"
    echo "  Vault:        $DIR/data/vault"
    echo "  Qdrant data:  $DIR/data/qdrant"
    echo ""
    echo "Python: $DIR/.venv/bin/python3"
    echo "venv exists: $(test -f "$DIR/.venv/bin/python3" && echo "${G}yes${X}" || echo "${R}no${X}")"
    echo ""
    echo "Paths in current mcp.json: $(grep -c '/' "$MCP_CONFIG" 2>/dev/null || echo "0")"
    exit 0
fi

# ── Validate ───────────────────────────────────────────────────────

if [ ! -f "$TEMPLATE" ]; then
    echo "${R}Error: Template not found at $TEMPLATE${X}"
    exit 1
fi

if [ ! -f "$DIR/.venv/bin/python3" ]; then
    echo "${R}Error: Python venv not found at $DIR/.venv/bin/python3${X}"
    echo "  Run: python3 -m venv $DIR/.venv && $DIR/.venv/bin/pip install -r requirements.txt"
    exit 1
fi

# ── Generate mcp.json ──────────────────────────────────────────────

echo "${B}🔧 Generating portable configuration${X}"
echo "  MEMORY_SERVER_DIR = $DIR"

MCP_JSON=$(sed \
    -e "s|{{DIR}}|$DIR|g" \
    -e "s|{{QDRANT_URL}}|$QDRANT_URL|g" \
    -e "s|{{LLAMA_SERVER_URL}}|$LLAMA_SERVER_URL|g" \
    -e "s|{{LLM_BACKEND}}|$LLM_BACKEND|g" \
    -e "s|{{LLM_MODEL}}|$LLM_MODEL|g" \
    "$TEMPLATE")

# Validate JSON
echo "$MCP_JSON" | python3 -m json.tool > /dev/null 2>&1 || {
    echo "${R}Error: Generated invalid JSON${X}"
    exit 1
}

OLD_PATHS=$(grep -c '/Users/' "$MCP_CONFIG" 2>/dev/null || echo "0")
NEW_PATHS=$(echo "$MCP_JSON" | grep -c '/Users/' || echo "0")

echo "  Old absolute paths: $OLD_PATHS"
echo "  New absolute paths: $NEW_PATHS (only python/cmd paths — data paths derived at runtime)"

if $DRY_RUN; then
    echo ""
    echo "${Y}DRY RUN — would write to:$X $MCP_CONFIG"
    echo "$MCP_JSON" | python3 -m json.tool
    exit 0
fi

# Backup old config
if [ -f "$MCP_CONFIG" ]; then
    cp "$MCP_CONFIG" "$MCP_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
    echo "  Backed up old config"
fi

# Write
mkdir -p "$(dirname "$MCP_CONFIG")"
echo "$MCP_JSON" | python3 -m json.tool > "$MCP_CONFIG"
echo "  ${G}✅ Written to $MCP_CONFIG${X}"

# ── Generate launchd plists ────────────────────────────────────────

echo ""
echo "${B}🔧 Generating launchd plists${X}"

LAUNCH_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_DIR"
mkdir -p "$HOME/.memory"

PLISTS_GENERATED=0

# --- Qdrant ---
QDRANT_PLIST="$LAUNCH_DIR/com.agent-memory.qdrant.plist"
cat > "$QDRANT_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.agent-memory.qdrant</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DIR/src/shared/qdrant/start.sh</string>
    </array>
    <key>WorkingDirectory</key><string>$DIR/src/shared/qdrant</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/qdrant.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/qdrant-error.log</string>
    <key>ThrottleInterval</key><integer>5</integer>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
echo "  ✅ com.agent-memory.qdrant.plist"
((PLISTS_GENERATED++))

# --- llama-server ---
LLAMA_BIN="$DIR/bin/engine/bin/llama-server"
LLAMA_MODEL="$DIR/bin/models/bge-m3-q8_0.gguf"
# Fallback to Q4 if Q8 not available
if [ ! -f "$LLAMA_MODEL" ] && [ -f "$DIR/bin/models/bge-m3-Q4_K_M.gguf" ]; then
    LLAMA_MODEL="$DIR/bin/models/bge-m3-Q4_K_M.gguf"
fi
LLAMA_LIB="$DIR/bin/engine/lib"

if [ -f "$LLAMA_BIN" ] && [ -f "$LLAMA_MODEL" ]; then
    LLAMA_PLIST="$LAUNCH_DIR/com.agent-memory.llama-embedding.plist"
    cat > "$LLAMA_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.agent-memory.llama-embedding</string>
    <key>ProgramArguments</key>
    <array>
        <string>$LLAMA_BIN</string>
        <string>-m</string><string>$LLAMA_MODEL</string>
        <string>--port</string><string>$(echo "$LLAMA_SERVER_URL" | grep -o '[0-9]*$')</string>
        <string>--host</string><string>127.0.0.1</string>
        <string>--embedding</string>
        <string>--pooling</string><string>mean</string>
        <string>-c</string><string>8192</string>
        <string>-b</string><string>8192</string>
        <string>-ub</string><string>8192</string>
        <string>-np</string><string>3</string>
        <string>-t</string><string>4</string>
        <string>--log-disable</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DYLD_LIBRARY_PATH</key><string>$LLAMA_LIB</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/llama-embedding-server.log</string>
    <key>StandardErrorPath</key><string>/tmp/llama-embedding-server.err</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
    echo "  ✅ com.agent-memory.llama-embedding.plist"
    ((PLISTS_GENERATED++))
else
    echo "  ⚠️  llama-server binary/model not found, skipping plist"
fi

# --- Gateway ---
GATEWAY_PLIST="$LAUNCH_DIR/com.agent-memory.gateway.plist"
NODE_PATH="$(which node)"
ONE_MCP_PATH="$(which 1mcp)"
cat > "$GATEWAY_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.agent-memory.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>$NODE_PATH</string>
        <string>$ONE_MCP_PATH</string>
        <string>serve</string>
        <string>--port</string><string>$GATEWAY_PORT</string>
        <string>--enable-config-reload</string><string>false</string>
    </array>
    <key>WorkingDirectory</key><string>$DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ONE_MCP_CONFIG</key><string>$MCP_CONFIG</string>
        <key>PATH</key><string>$(dirname "$NODE_PATH"):/usr/bin:/usr/local/bin:/opt/homebrew/bin</string>
        <key>HOME</key><string>$HOME</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/gateway.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/gateway-error.log</string>
    <key>ThrottleInterval</key><integer>5</integer>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
echo "  ✅ com.agent-memory.gateway.plist"
((PLISTS_GENERATED++))

# --- Watchdog ---
WATCHDOG_PLIST="$LAUNCH_DIR/com.agent-memory.watchdog.plist"
cat > "$WATCHDOG_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.agent-memory.watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DIR/scripts/watchdog.sh</string>
    </array>
    <key>WorkingDirectory</key><string>$DIR</string>
    <key>StartInterval</key><integer>300</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$HOME/.memory/watchdog.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/watchdog-error.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
echo "  ✅ com.agent-memory.watchdog.plist"
((PLISTS_GENERATED++))

# ── Reload launchd ─────────────────────────────────────────────────

echo ""
echo "${B}🔄 Reloading launchd services${X}"

for plist in "$LAUNCH_DIR"/com.agent-memory.*.plist; do
    label="$(basename "$plist" .plist)"
    # Unload if loaded
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    # Load
    launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null && echo "  ✅ $label loaded" || echo "  ⚠️  $label — may need logout/login"
done

# ── Summary ────────────────────────────────────────────────────────

echo ""
echo "${B}═══════════════════════════════════════════${X}"
echo "${G}✅ Configuration complete!${X}"
echo ""
echo "  📁 MEMORY_SERVER_DIR: $DIR"
echo "  📋 MCP config:        $MCP_CONFIG"
echo "  📦 Launchd plists:     $PLISTS_GENERATED"
echo ""
echo "  Paths in mcp.json:    $OLD_PATHS → $NEW_PATHS (only python binary paths)"
echo "  Data paths derived:   at runtime by env_loader.py"
echo ""
echo "  ${B}To reconfigure on another machine:${X}"
echo "  MEMORY_SERVER_DIR=/new/path scripts/configure.sh"
echo "${B}═══════════════════════════════════════════${X}"
