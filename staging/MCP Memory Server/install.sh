#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════
# MCP Memory Server — Self-Contained Installer
#
# Installs to: ~/MCP-servers/MCP-memory-server/ (default)
# Everything bundled: Qdrant, llama.cpp engine, model, Python venv
# No Homebrew. No Docker. No external dependencies.
# ═══════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Installer                        ║"
echo "║   Self-contained · No Docker · No Homebrew             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Ask install location ──────────────────────────────────────────

DEFAULT_DIR="$HOME/MCP-servers/MCP-memory-server"
echo "Install location [$DEFAULT_DIR]:"
read -r INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

echo ""
echo "Installing to: $INSTALL_DIR"
echo ""

# ── Check prerequisites ──────────────────────────────────────────

MISSING=0

# Python 3.10+
if command -v python3.12 &> /dev/null; then
    PY_CMD="python3.12"
elif command -v python3.11 &> /dev/null; then
    PY_CMD="python3.11"
elif command -v python3.10 &> /dev/null; then
    PY_CMD="python3.10"
elif python3 --version 2>/dev/null | grep -qE "3\.(1[0-9]|[2-9][0-9])"; then
    PY_CMD="python3"
else
    echo "  ✗ Python 3.10+ required"
    MISSING=1
fi

if [ "$MISSING" -eq 0 ]; then
    echo "  ✓ $($PY_CMD --version 2>&1)"
fi

# Node.js (optional, for 1MCP gateway)
NODE_BIN=""
if command -v node &> /dev/null; then
    NODE_BIN=$(which node)
    echo "  ✓ Node.js $(node --version) (optional — for HTTP gateway)"
fi

if [ "$MISSING" -eq 1 ]; then
    echo "Missing Python 3.10+. Install it and run again."
    exit 1
fi

# ── Detect platform ──────────────────────────────────────────────

MACHINE=$(uname -m)
OS=$(uname -s)
echo ""
echo "Platform: $OS $MACHINE"

# ── Create directory structure ────────────────────────────────────

echo ""
echo "Creating directory structure..."
mkdir -p "$INSTALL_DIR"/{engine/{bin,lib},models,servers/{automem,autodream,vk-cache,conversation-store,mem0-bridge,engram-bridge,sequential-thinking}/server,shared/{models,qdrant},config,skills/{memory-core,research,code,filesystem}}

# ── Copy engine (llama.cpp + libs) ───────────────────────────────

echo ""
echo "Installing bundled engine..."
ENGINE_SRC="$(cd "$(dirname "$0")" && pwd)/engine"

if [ -d "$ENGINE_SRC" ] && [ -f "$ENGINE_SRC/bin/llama-embedding" ]; then
    cp -R "$ENGINE_SRC/bin"/* "$INSTALL_DIR/engine/bin/"
    cp -R "$ENGINE_SRC/lib"/* "$INSTALL_DIR/engine/lib/" 2>/dev/null || true
    echo "  ✓ llama.cpp engine copied"
    echo "  ✓ $(ls "$INSTALL_DIR/engine/lib/" | wc -l) libraries bundled"
else
    echo "  ✗ Engine not found in installer package."
    echo "    This installer requires a pre-built engine/ directory."
    exit 1
fi

# Re-sign all binaries (required after copy on macOS)
if [ "$OS" = "Darwin" ]; then
    echo "  → Re-signing binaries..."
    codesign --force --sign - --deep "$INSTALL_DIR/engine/bin/llama-embedding" 2>/dev/null || true
    for lib in "$INSTALL_DIR/engine/lib/"*.dylib; do
        [ -f "$lib" ] && codesign --force --sign - "$lib" 2>/dev/null || true
    done
    echo "  ✓ Binaries signed"
fi

# ── Copy embedding model ──────────────────────────────────────────

echo ""
echo "Installing embedding model..."
MODEL_SRC="$(cd "$(dirname "$0")" && pwd)/models"
if [ -d "$MODEL_SRC" ] && ls "$MODEL_SRC/"*.gguf &>/dev/null; then
    cp "$MODEL_SRC/"*.gguf "$INSTALL_DIR/models/"
    MODEL_SIZE=$(du -sh "$INSTALL_DIR/models/"*.gguf | head -1 | awk '{print $1}')
    echo "  ✓ Model copied ($MODEL_SIZE)"
else
    echo "  ✗ No .gguf model found in installer package."
    echo "    Download it:"
    echo "    huggingface-cli download LLukas22/all-MiniLM-L6-v2-GGUF"
    echo "    --include '*.gguf' --local-dir '$INSTALL_DIR/models'"
    exit 1
fi

# ── Copy Qdrant ───────────────────────────────────────────────────

echo ""
echo "Installing Qdrant vector store..."
QDRANT_SRC="$(cd "$(dirname "$0")" && pwd)/shared/qdrant"
QDRANT_BIN_SRC="$(cd "$(dirname "$0")" && pwd)/shared/qdrant/qdrant"

if [ -f "$QDRANT_BIN_SRC" ]; then
    cp "$QDRANT_BIN_SRC" "$INSTALL_DIR/bin/qdrant" 2>/dev/null || {
        mkdir -p "$INSTALL_DIR/bin"
        cp "$QDRANT_BIN_SRC" "$INSTALL_DIR/bin/qdrant"
    }
    echo "  ✓ Qdrant binary copied"

    # Re-sign
    if [ "$OS" = "Darwin" ]; then
        codesign --force --sign - "$INSTALL_DIR/bin/qdrant" 2>/dev/null || true
    fi
else
    echo "  ⚠ Qdrant binary not found in package."
fi

# Qdrant config + start script
if [ -f "$QDRANT_SRC/config.yaml" ]; then
    cp "$QDRANT_SRC/config.yaml" "$INSTALL_DIR/shared/qdrant/"
fi

cat > "$INSTALL_DIR/shared/qdrant/start.sh" << 'SCRIPT'
#!/bin/bash
ulimit -n 10240
export MALLOC_CONF="background_thread:false,narenas:1"
cd "$(dirname "$0")"
mkdir -p data snapshots
# Find qdrant binary
QDRANT_BIN=""
if [ -f "./qdrant" ]; then
    QDRANT_BIN="./qdrant"
elif [ -f "../../bin/qdrant" ]; then
    QDRANT_BIN="../../bin/qdrant"
elif command -v qdrant &>/dev/null; then
    QDRANT_BIN="qdrant"
else
    echo "ERROR: qdrant binary not found"
    exit 1
fi
exec "$QDRANT_BIN" --config-path config.yaml
SCRIPT
chmod +x "$INSTALL_DIR/shared/qdrant/start.sh"

# ── Copy server code ─────────────────────────────────────────────

echo ""
echo "Installing MCP servers..."
SERVERS_SRC="$(cd "$(dirname "$0")" && pwd)/servers"

if [ -d "$SERVERS_SRC" ]; then
    for server in automem autodream vk-cache conversation-store mem0-bridge engram-bridge sequential-thinking; do
        if [ -f "$SERVERS_SRC/$server/server/main.py" ]; then
            cp "$SERVERS_SRC/$server/server/main.py" "$INSTALL_DIR/servers/$server/server/"
            echo "  ✓ $server"
        fi
    done
else
    # Fall back to sibling directories (dev mode)
    DEV_SRC="$(cd "$(dirname "$0")" && pwd)"
    for server in automem autodream vk-cache conversation-store mem0-bridge engram-bridge sequential-thinking; do
        if [ -f "$DEV_SRC/$server/server/main.py" ]; then
            cp "$DEV_SRC/$server/server/main.py" "$INSTALL_DIR/servers/$server/server/"
            echo "  ✓ $server"
        fi
    done
fi

# Copy shared modules
cp "$(cd "$(dirname "$0")" && pwd)/shared/"*.py "$INSTALL_DIR/shared/" 2>/dev/null || true
echo "  ✓ shared modules"

# ── Python venv + dependencies ────────────────────────────────────

echo ""
echo "Setting up Python environment..."
$PY_CMD -m venv "$INSTALL_DIR/.venv"
source "$INSTALL_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet mcp pydantic httpx huggingface_hub
echo "  ✓ Python packages installed"

# ── Configuration ──────────────────────────────────────────────────

echo ""
echo "Creating configuration..."

PYTHON_VENV="$INSTALL_DIR/.venv/bin/python3"
cat > "$INSTALL_DIR/config/.env" << EOF
# MCP Memory Server — Configuration
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=automem
CONV_COLLECTION=conversations
MEM0_COLLECTION=mem0_memories
EMBEDDING_DIM=384
MEMORY_SERVER_DIR=$INSTALL_DIR
DREAM_PATH=$HOME/.memory/dream
ENGRAM_PATH=$HOME/.memory/engram
AUTOMEM_JSONL=$HOME/.memory/raw_events.jsonl
PYTHONPATH=$INSTALL_DIR
VK_MIN_SCORE=0.3
VK_MAX_ITEMS=8
VK_MAX_TOKENS=8000
EOF

# mcp.json for 1MCP gateway
cat > "$INSTALL_DIR/config/mcp.json" << EOF
{
  "mcpServers": {
    "automem": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/automem/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "ingest"], "disabled": false
    },
    "autodream": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/autodream/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "consolidation"], "disabled": false
    },
    "vk-cache": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/vk-cache/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "retrieval"], "disabled": false
    },
    "conversation-store": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/conversation-store/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "conversations"], "disabled": false
    },
    "mem0-bridge": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/mem0-bridge/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "semantic"], "disabled": false
    },
    "engram-bridge": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/engram-bridge/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["memory", "decisions"], "disabled": false
    },
    "sequential-thinking": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/sequential-thinking/server/main.py"],
      "env": {"PYTHONPATH": "$INSTALL_DIR", "MEMORY_SERVER_DIR": "$INSTALL_DIR"},
      "tags": ["reasoning", "planning"], "disabled": false
    }
  }
}
EOF

echo "  ✓ config/.env"
echo "  ✓ config/mcp.json"

# ── Data directories ─────────────────────────────────────────────

mkdir -p "$HOME/.memory"/{raw,engram,dream,heartbeats,reminders,thoughts}
echo "  ✓ ~/.memory/ data directories"

# ── Install system services ───────────────────────────────────────

if [ "$OS" = "Darwin" ]; then
    echo ""
    echo "Installing system services..."

    # Qdrant launchd
    cat > "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.qdrant</string>
    <key>ProgramArguments</key>
    <array><string>$INSTALL_DIR/shared/qdrant/start.sh</string></array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR/shared/qdrant</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/qdrant.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/qdrant-error.log</string>
    <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
PLIST
    launchctl unload "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist" 2>/dev/null || true
    launchctl load "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist"
    echo "  ✓ Qdrant service installed"

    # Gateway service (if Node.js available)
    if [ -n "$NODE_BIN" ] && [ -d "$INSTALL_DIR/1mcp-agent" ]; then
        cat > "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>$NODE_BIN</string>
        <string>$INSTALL_DIR/1mcp-agent/build/index.js</string>
        <string>serve</string><string>--port</string><string>3050</string>
        <string>--enable-config-reload</string><string>false</string>
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR/1mcp-agent</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/gateway.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/gateway-error.log</string>
    <key>ThrottleInterval</key><integer>5</integer>
</dict>
</plist>
PLIST
        launchctl load "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" 2>/dev/null || true
        echo "  ✓ Gateway service installed"
    fi
fi

# ── Start and verify ─────────────────────────────────────────────

echo ""
echo "Starting services..."
sleep 5

QDRANT_OK=false
for i in 1 2 3 4 5; do
    if curl -s http://127.0.0.1:6333/collections > /dev/null 2>&1; then
        QDRANT_OK=true
        break
    fi
    sleep 2
done

if $QDRANT_OK; then
    echo "  ✓ Qdrant running on :6333"
    # Create collections
    for coll in automem conversations mem0_memories; do
        curl -s -X PUT "http://127.0.0.1:6333/collections/$coll" \
            -H "Content-Type: application/json" \
            -d '{"vectors":{"size":384,"distance":"Cosine"}}' > /dev/null
    done
    echo "  ✓ Collections created"

    # Test engine
    echo "  Testing bundled engine..."
    TEST_RESULT=$(DYLD_LIBRARY_PATH="$INSTALL_DIR/engine/lib" \
        "$INSTALL_DIR/engine/bin/llama-embedding" \
        -m "$INSTALL_DIR/models/"*.gguf \
        -p "installation test" --log-disable 2>/dev/null)
    if echo "$TEST_RESULT" | grep -q "embedding"; then
        echo "  ✓ Engine working"
    fi
else
    echo "  ⚠ Qdrant not responding yet"
fi

# ── Summary ───────────────────────────────────────────────────────

TOTAL_SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | awk '{print $1}')

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Installation Complete!                                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location:    $INSTALL_DIR ($TOTAL_SIZE)"
echo "  Engine:      $INSTALL_DIR/engine/"
echo "  Model:       $INSTALL_DIR/models/"
echo "  Qdrant:      http://127.0.0.1:6333"
echo "  Services:    launchd (auto-start on boot)"
echo "  Logs:        ~/.memory/*.log"
echo ""
echo "  Start a server:"
echo "    source $INSTALL_DIR/.venv/bin/activate"
echo "    cd $INSTALL_DIR/servers/automem/server && python3 main.py"
echo ""
echo "  Test engine:"
echo "    DYLD_LIBRARY_PATH=$INSTALL_DIR/engine/lib \\"
echo "    $INSTALL_DIR/engine/bin/llama-embedding -m $INSTALL_DIR/models/*.gguf -p 'hello' --log-disable"
echo ""
