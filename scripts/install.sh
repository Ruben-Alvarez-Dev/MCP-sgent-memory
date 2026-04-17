#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════
# MCP Memory Server — Self-Contained Installer
#
# Installs to: ~/MCP-servers/MCP-memory-server/
#
# Bundled: Qdrant, llama.cpp engine, BGE-M3 model, Python venv, vault
# No Homebrew. No Docker. No external dependencies.
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Installer                        ║"
echo "║   Hybrid Search · LLM Agnostic · Obsidian Vault        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Ask install location ──────────────────────────────────────────

DEFAULT_DIR="$HOME/MCP-servers/MCP-memory-server"
echo "Install location [$DEFAULT_DIR]:"
read -r INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

if [ -d "$INSTALL_DIR" ]; then
    echo ""
    echo "  ⚠ Directory already exists: $INSTALL_DIR"
    echo "  Do you want to OVERWRITE the installation? (y/N)"
    read -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    
    # Backup tools.db if it exists
    if [ -f "$INSTALL_DIR/tests/e2e/tools.db" ]; then
        echo "  📦 Backing up tools.db..."
        cp "$INSTALL_DIR/tests/e2e/tools.db" "$INSTALL_DIR/tests/e2e/tools.db.bak-$(date +%Y%m%d%H%M%S)"
    fi
fi

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
mkdir -p "$INSTALL_DIR"/engine/bin "$INSTALL_DIR"/engine/lib
mkdir -p "$INSTALL_DIR"/models
mkdir -p "$INSTALL_DIR"/servers/{automem,autodream,vk-cache,conversation-store,mem0-bridge,engram-bridge,sequential-thinking}/server
mkdir -p "$INSTALL_DIR"/shared/{llm,retrieval,compliance,vault_manager,models}
mkdir -p "$INSTALL_DIR"/config
mkdir -p "$INSTALL_DIR"/vault/{Inbox,"Decisiones","Conocimiento",Episodios,Log_Global,Entidades,Personas,Templates}
mkdir -p "$INSTALL_DIR"/vault/.system/{locks,backups,trash/{human-deleted,system-deleted},orphaned}
mkdir -p "$INSTALL_DIR"/tests

# ── Copy engine (llama.cpp) ──────────────────────────────────────

echo ""
echo "Installing bundled engine..."
ENGINE_SRC="$SCRIPT_DIR/engine"

if [ -d "$ENGINE_SRC" ] && [ -f "$ENGINE_SRC/bin/llama-embedding" ]; then
    cp -R "$ENGINE_SRC/bin/"* "$INSTALL_DIR/engine/bin/"
    cp -R "$ENGINE_SRC/lib/"* "$INSTALL_DIR/engine/lib/" 2>/dev/null || true
    echo "  ✓ llama.cpp engine copied"
    echo "  ✓ $(ls "$INSTALL_DIR/engine/lib/" 2>/dev/null | wc -l | tr -d ' ') libraries bundled"
else
    echo "  ✗ Engine not found in installer package."
    echo "    This installer requires a pre-built engine/ directory."
    exit 1
fi

# Copy llama-server binary if available
if [ -f "$ENGINE_SRC/bin/llama-server" ]; then
    cp "$ENGINE_SRC/bin/llama-server" "$INSTALL_DIR/engine/bin/"
    echo "  ✓ llama-server copied"
fi

# Re-sign all binaries (required after copy on macOS)
if [ "$OS" = "Darwin" ]; then
    echo "  → Re-signing binaries..."
    codesign --force --sign - --deep "$INSTALL_DIR/engine/bin/llama-embedding" 2>/dev/null || true
    if [ -f "$INSTALL_DIR/engine/bin/llama-server" ]; then
        codesign --force --sign - "$INSTALL_DIR/engine/bin/llama-server" 2>/dev/null || true
    fi
    for lib in "$INSTALL_DIR/engine/lib/"*.dylib; do
        [ -f "$lib" ] && codesign --force --sign - "$lib" 2>/dev/null || true
    done
    echo "  ✓ Binaries signed"
fi

# ── Copy embedding model ──────────────────────────────────────────

echo ""
echo "Installing embedding model (BGE-M3)..."
MODEL_SRC="$SCRIPT_DIR/models"
if [ -d "$MODEL_SRC" ] && ls "$MODEL_SRC/"*.gguf &>/dev/null; then
    cp "$MODEL_SRC/"*.gguf "$INSTALL_DIR/models/"
    MODEL_SIZE=$(du -sh "$INSTALL_DIR/models/"*.gguf | head -1 | awk '{print $1}')
    echo "  ✓ Model copied ($MODEL_SIZE)"
else
    echo "  ⚠ No .gguf model found in installer package."
    echo "    The system will fall back to MiniLM if available."
fi

# ── Copy Qdrant ───────────────────────────────────────────────────

echo ""
echo "Installing Qdrant vector store..."
QDRANT_SRC="$SCRIPT_DIR/shared/qdrant"
QDRANT_BIN_SRC="$SCRIPT_DIR/shared/qdrant/qdrant"

if [ -f "$QDRANT_BIN_SRC" ]; then
    mkdir -p "$INSTALL_DIR/bin"
    cp "$QDRANT_BIN_SRC" "$INSTALL_DIR/bin/qdrant"
    echo "  ✓ Qdrant binary copied"

    if [ "$OS" = "Darwin" ]; then
        codesign --force --sign - "$INSTALL_DIR/bin/qdrant" 2>/dev/null || true
    fi
else
    echo "  ⚠ Qdrant binary not found in package."
fi

# Qdrant config
if [ -f "$QDRANT_SRC/config.yaml" ]; then
    mkdir -p "$INSTALL_DIR/shared/qdrant"
    cp "$QDRANT_SRC/config.yaml" "$INSTALL_DIR/shared/qdrant/"
fi

cat > "$INSTALL_DIR/shared/qdrant/start.sh" << 'SCRIPT'
#!/bin/bash
ulimit -n 10240
export MALLOC_CONF="background_thread:false,narenas:1"
cd "$(dirname "$0")"
mkdir -p data snapshots
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
SERVERS_SRC="$SCRIPT_DIR/servers"

for server in automem autodream vk-cache conversation-store mem0-bridge engram-bridge sequential-thinking; do
    if [ -d "$SERVERS_SRC/$server" ]; then
        cp -R "$SERVERS_SRC/$server/"* "$INSTALL_DIR/servers/$server/" 2>/dev/null || true
        echo "  ✓ $server (full directory)"
    elif [ -f "$SCRIPT_DIR/$server/server/main.py" ]; then
        # Fallback: dev mode structure
        mkdir -p "$INSTALL_DIR/servers/$server/server"
        cp "$SCRIPT_DIR/$server/server/main.py" "$INSTALL_DIR/servers/$server/server/"
        echo "  ✓ $server (main.py only)"
    else
        echo "  ⚠ $server not found"
    fi
done

# Copy shared modules (full packages)
echo ""
echo "Installing shared modules..."
for pkg in llm retrieval compliance vault_manager models; do
    if [ -d "$SCRIPT_DIR/shared/$pkg" ]; then
        cp -R "$SCRIPT_DIR/shared/$pkg" "$INSTALL_DIR/shared/"
        echo "  ✓ shared/$pkg"
    fi
done

# Copy individual shared files
for f in embedding.py __init__.py; do
    if [ -f "$SCRIPT_DIR/shared/$f" ]; then
        cp "$SCRIPT_DIR/shared/$f" "$INSTALL_DIR/shared/"
        echo "  ✓ shared/$f"
    fi
done

# Copy vault templates
if [ -d "$SCRIPT_DIR/vault/Templates" ]; then
    cp "$SCRIPT_DIR/vault/Templates/"* "$INSTALL_DIR/vault/Templates/" 2>/dev/null || true
    echo "  ✓ vault templates"
fi

# ── Python venv + dependencies ────────────────────────────────────

echo ""
echo "Setting up Python environment..."
$PY_CMD -m venv "$INSTALL_DIR/.venv"
source "$INSTALL_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet mcp pydantic httpx pyyaml huggingface_hub
echo "  ✓ Python packages installed"

# ── Configuration ──────────────────────────────────────────────────

echo ""
echo "Creating configuration..."

PYTHON_VENV="$INSTALL_DIR/.venv/bin/python3"

# Detect available LLM backend
LLM_BACKEND="ollama"
LLM_MODEL="qwen2.5:7b"
SMALL_LLM_MODEL="qwen3.5:2b"

cat > "$INSTALL_DIR/config/.env" << EOF
# MCP Memory Server — Configuration
# Generated by installer on $(date '+%Y-%m-%d %H:%M:%S')

# ── Shared Infrastructure ──────────────────────────────────────────
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=automem
CONV_COLLECTION=conversations
MEM0_COLLECTION=mem0_memories

# ── Embedding ──────────────────────────────────────────────────────
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024

# ── LLM Backend (agnostic) ─────────────────────────────────────────
LLM_BACKEND=$LLM_BACKEND
LLM_MODEL=$LLM_MODEL
SMALL_LLM_MODEL=$SMALL_LLM_MODEL

# ── Ollama ─────────────────────────────────────────────────────────
OLLAMA_URL=http://127.0.0.1:11434

# ── LM Studio (alternative backend) ────────────────────────────────
# LMSTUDIO_URL=http://127.0.0.1:1234

# ── Vault ──────────────────────────────────────────────────────────
VAULT_PATH=$INSTALL_DIR/vault

# ── Paths ──────────────────────────────────────────────────────────
DREAM_PATH=\$HOME/.memory/dream
ENGRAM_PATH=\$HOME/.memory/engram
AUTOMEM_JSONL=\$HOME/.memory/raw_events.jsonl
MEMORY_SERVER_DIR=$INSTALL_DIR
PYTHONPATH=$INSTALL_DIR

# ── vk-cache ───────────────────────────────────────────────────────
VK_MIN_SCORE=0.3
VK_MAX_ITEMS=8
VK_MAX_TOKENS=8000

# ── AutoDream schedules ────────────────────────────────────────────
DREAM_PROMOTE_L1=10
DREAM_PROMOTE_L2=3600
DREAM_PROMOTE_L3=86400
DREAM_PROMOTE_L4=604800
EOF

# mcp.json for 1MCP gateway
cat > "$INSTALL_DIR/config/mcp.json" << EOF
{
  "mcpServers": {
    "automem": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/automem/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      },
      "tags": ["memory", "ingest"],
      "disabled": false
    },
    "autodream": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/autodream/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "LLM_BACKEND": "$LLM_BACKEND",
        "LLM_MODEL": "$LLM_MODEL"
      },
      "tags": ["memory", "consolidation"],
      "disabled": false
    },
    "vk-cache": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/vk-cache/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "ENGRAM_PATH": "\$HOME/.memory/engram",
        "VAULT_PATH": "$INSTALL_DIR/vault"
      },
      "tags": ["memory", "retrieval"],
      "disabled": false
    },
    "conversation-store": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/conversation-store/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333"
      },
      "tags": ["memory", "conversations"],
      "disabled": false
    },
    "mem0-bridge": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/mem0-bridge/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333"
      },
      "tags": ["memory", "semantic"],
      "disabled": false
    },
    "engram-bridge": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/engram-bridge/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "VAULT_PATH": "$INSTALL_DIR/vault"
      },
      "tags": ["memory", "decisions", "vault"],
      "disabled": false
    },
    "sequential-thinking": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/servers/sequential-thinking/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR"
      },
      "tags": ["reasoning", "planning"],
      "disabled": false
    }
  }
}
EOF

# ── Install Qdrant as launchd service ─────────────────────────────

echo ""
echo "Setting up launchd services..."

if [ "$OS" = "Darwin" ]; then
    # Qdrant
    cat > "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.qdrant</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/shared/qdrant/start.sh</string>
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR/shared/qdrant</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/qdrant.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/qdrant-error.log</string>
</dict>
</plist>
PLIST

    launchctl unload "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist" 2>/dev/null || true
    launchctl load "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist"
    echo "  ✓ Qdrant service installed"

    # Create .memory dirs
    mkdir -p "$HOME/.memory"/{dream,engram,raw_events.jsonl} 2>/dev/null || true

    echo ""
    echo "Waiting for Qdrant to start..."
    sleep 3
    if curl -s http://127.0.0.1:6333/health &>/dev/null; then
        echo "  ✓ Qdrant is running"
    else
        echo "  ⚠ Qdrant may not be running yet. Check: launchctl list | grep memory-server"
    fi

    # Create collections with sparse_vectors
    echo ""
    echo "Creating Qdrant collections..."
    for col in automem conversations mem0_memories; do
        curl -s -X DELETE "http://127.0.0.1:6333/collections/$col" &>/dev/null || true
        curl -s -X PUT "http://127.0.0.1:6333/collections/$col" \
            -H "Content-Type: application/json" \
            -d '{"vectors":{"size":1024,"distance":"Cosine"},"sparse_vectors":{"text":{"index":{"type":"bm25"}}}}' \
            &>/dev/null
        if [ $? -eq 0 ]; then
            echo "  ✓ $col (dense=1024d + sparse=BM25)"
        else
            echo "  ⚠ Failed to create $col"
        fi
    done
else
    echo "  ⚠ Non-macOS platform. Start Qdrant manually."
fi

# ── Install 1MCP Gateway ──────────────────────────────────────────

echo ""
echo "Setting up 1MCP Gateway..."

# Check Node.js (prerequisite)
GATEWAY_AVAILABLE=true
if command -v node &>/dev/null; then
    NODE_CMD=$(command -v node)
    NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    echo "  ✓ Node.js v$NODE_VERSION"
    if [ "$NODE_MAJOR" -lt 18 ] 2>/dev/null; then
        echo "  ⚠ Node.js 18+ required, found v$NODE_VERSION"
        GATEWAY_AVAILABLE=false
    fi
else
    echo "  ⚠ Node.js not found. Installing via Homebrew..."
    if command -v brew &>/dev/null; then
        brew install node 2>&1 | tail -3
        if command -v node &>/dev/null; then
            NODE_CMD=$(command -v node)
            echo "  ✓ Node.js installed: $(node --version)"
        else
            echo "  ✗ Node.js install failed. Gateway cannot be installed."
            GATEWAY_AVAILABLE=false
        fi
    else
        echo "  ✗ Homebrew not found. Install Node.js manually and run again."
        GATEWAY_AVAILABLE=false
    fi
fi

# Check npm
if [ "$GATEWAY_AVAILABLE" = "true" ]; then
    if ! command -v npm &>/dev/null; then
        echo "  ✗ npm not found. Required for gateway installation."
        GATEWAY_AVAILABLE=false
    fi
fi

if [ "$GATEWAY_AVAILABLE" = "true" ]; then
    # Install 1mcp globally via npm (handles all dependencies)
    if command -v 1mcp &>/dev/null; then
        echo "  ✓ 1mcp already installed globally ($(1mcp --version 2>/dev/null || echo 'unknown'))"
    else
        echo "  → Installing @1mcp/agent globally..."
        npm install -g @1mcp/agent 2>&1 | tail -1
        if command -v 1mcp &>/dev/null; then
            echo "  ✓ 1mcp installed: $(which 1mcp)"
        else
            echo "  ⚠ 1mcp install may have failed. Continuing anyway."
        fi
    fi

    # Copy mcp.json (generated earlier) to global config
    mkdir -p "$HOME/.config/1mcp"
    cp "$INSTALL_DIR/config/mcp.json" "$HOME/.config/1mcp/mcp.json"
    echo "  ✓ mcp.json → $HOME/.config/1mcp/mcp.json"

    # Find the actual node binary (launchd needs absolute paths, can't resolve shebangs)
    if command -v node &>/dev/null; then
        GATEWAY_NODE=$(command -v node)
    elif [ -f "/opt/homebrew/bin/node" ]; then
        GATEWAY_NODE="/opt/homebrew/bin/node"
    else
        GATEWAY_NODE="$NODE_CMD"
    fi

    # Find the 1mcp binary
    if command -v 1mcp &>/dev/null; then
        GATEWAY_BIN=$(command -v 1mcp)
        # Check if it's a shell wrapper (nvm style) with #!/usr/bin/env node shebang
        FIRST_LINE=$(head -1 "$GATEWAY_BIN" 2>/dev/null || echo "")
        if echo "$FIRST_LINE" | grep -q "env node"; then
            # It's a wrapper script — call node directly with the script path
            GATEWAY_EXEC="$GATEWAY_NODE"
            GATEWAY_ARGS=("$GATEWAY_BIN" "serve" "--port" "3050" "--enable-config-reload" "false")
        else
            # It's a standalone binary
            GATEWAY_EXEC="$GATEWAY_BIN"
            GATEWAY_ARGS=("serve" "--port" "3050" "--enable-config-reload" "false")
        fi
    else
        # Fallback: try to find build/index.js in global node_modules
        GLOBAL_PREFIXES=("$(npm root -g 2>/dev/null)/@1mcp/agent/build/index.js")
        GATEWAY_EXEC="$GATEWAY_NODE"
        for p in "${GLOBAL_PREFIXES[@]}"; do
            if [ -f "$p" ]; then
                GATEWAY_ARGS=("$p" "serve" "--port" "3050" "--enable-config-reload" "false")
                break
            fi
        done
        if [ -z "${GATEWAY_ARGS+x}" ]; then
            echo "  ⚠ 1mcp binary not found. Gateway service will not start."
            GATEWAY_AVAILABLE=false
        fi
    fi
fi

if [ "$GATEWAY_AVAILABLE" = "true" ]; then
    GATEWAY_NODE_DIR=$(dirname "$GATEWAY_NODE")
    NODE_PATH_FOR_GW="$(dirname "$GATEWAY_BIN"):$GATEWAY_NODE_DIR"

    # Create gateway launchd service
    cat > "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>$GATEWAY_EXEC</string>
PLIST

    for arg in "${GATEWAY_ARGS[@]}"; do
        echo "        <string>$arg</string>" >> "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist"
    done

    cat >> "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" << PLIST
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/gateway.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/gateway-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ONE_MCP_CONFIG</key>
        <string>$HOME/.config/1mcp/mcp.json</string>
        <key>PATH</key>
        <string>$NODE_PATH_FOR_GW:/usr/bin:/usr/local/bin:/opt/homebrew/bin</string>
    </dict>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
PLIST

    # Create start-gateway.sh for manual use
    cat > "$INSTALL_DIR/start-gateway.sh" << SCRIPT
#!/bin/bash
export ONE_MCP_CONFIG="$HOME/.config/1mcp/mcp.json"
export MEMORY_SERVER_DIR="$INSTALL_DIR"
export PATH="$NODE_PATH_FOR_GW:/usr/bin:/usr/local/bin:/opt/homebrew/bin:\$PATH"
cd "$INSTALL_DIR"
exec $GATEWAY_EXEC ${GATEWAY_ARGS[*]}
SCRIPT
    chmod +x "$INSTALL_DIR/start-gateway.sh"

    # Remove old dev gateway if present
    launchctl unload "$HOME/Library/LaunchAgents/com.memory.mcp-gateway.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.memory.mcp-gateway.plist" 2>/dev/null || true

    # Load new gateway
    launchctl unload "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" 2>/dev/null || true
    launchctl load "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist"
    echo "  ✓ Gateway service installed"

    # Wait for gateway
    echo ""
    echo "Waiting for Gateway to start..."
    GATEWAY_HEALTHY=false
    for i in $(seq 1 20); do
        if curl -s --connect-timeout 2 http://127.0.0.1:3050/health &>/dev/null; then
            HEALTHY=$(curl -s http://127.0.0.1:3050/health 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"{d['servers']['healthy']}/{d['servers']['total']}\")
except: print('0/0')
" 2>/dev/null)
            echo "  ✓ Gateway running on http://127.0.0.1:3050 ($HEALTHY servers)"
            GATEWAY_HEALTHY=true
            break
        fi
        sleep 1
    done
    if [ "$GATEWAY_HEALTHY" != "true" ]; then
        echo "  ⚠ Gateway not ready yet. Starting manually..."
        "$INSTALL_DIR/start-gateway.sh" &>/dev/null &
        sleep 12
        if curl -s --connect-timeout 3 http://127.0.0.1:3050/health &>/dev/null; then
            echo "  ✓ Gateway started manually"
            GATEWAY_HEALTHY=true
        else
            echo "  ⚠ Gateway still not responding. Check: $HOME/.memory/gateway-error.log"
        fi
    fi
else
    echo ""
    echo "  ⚠ Gateway skipped (Node.js unavailable)"
    echo "    The MCP servers work standalone. Install Node.js 18+ later and run:"
    echo "    npm install -g @1mcp/agent"
    echo "    Then copy $INSTALL_DIR/config/mcp.json to ~/.config/1mcp/mcp.json"
fi

# ── Copy tools database ───────────────────────────────────────────

if [ -f "$SCRIPT_DIR/tools.db" ]; then
    mkdir -p "$INSTALL_DIR/tests/e2e"
    cp "$SCRIPT_DIR/tools.db" "$INSTALL_DIR/tests/e2e/tools.db"
    echo "  ✓ AI tools database copied ($(sqlite3 "$INSTALL_DIR/tests/e2e/tools.db" 'SELECT COUNT(*) FROM tools;' 2>/dev/null || echo '?') tools)"
fi

# ── MCP Client Config Helper ──────────────────────────────────────

cat > "$INSTALL_DIR/show-mcp-config.sh" << 'SHOWSCRIPT'
#!/bin/bash
# Show MCP client configuration for all supported agents
GATEWAY_URL="${1:-http://127.0.0.1:3050/mcp}"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Client Configuration              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Gateway: $GATEWAY_URL"
echo ""

echo "┌─── Claude Code ──────────────────────────────────────────┐"
echo "│ File: ~/.claude/mcp/memory.json                          │"
cat << 'EOF'
│ {
│   "mcpServers": {
│     "memory": {
│       "command": "curl",
│       "args": ["-s", "-X", "POST", "http://127.0.0.1:3050/mcp"]
│     }
│   }
│ }
│
│ Or via URL (Claude Code 2026+):
│ {
│   "mcpServers": {
│     "memory": {
│       "url": "http://127.0.0.1:3050/mcp",
│       "type": "http"
│     }
│   }
│ }
EOF
echo "└────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─── OpenCode ──────────────────────────────────────────────┐"
echo "│ File: ~/.config/opencode/opencode.json  → add to mcp:   │"
cat << 'EOF'
│ {
│   "mcp": {
│     "memory": {
│       "enabled": true,
│       "type": "remote",
│       "url": "http://127.0.0.1:3050/mcp"
│     }
│   }
│ }
EOF
echo "└────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─── Cursor ─────────────────────────────────────────────────┐"
echo "│ File: <project>/.cursor/mcp.json                          │"
cat << 'EOF'
│ {
│   "mcpServers": {
│     "memory": {
│       "url": "http://127.0.0.1:3050/mcp",
│       "type": "http"
│     }
│   }
│ }
EOF
echo "└────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─── VS Code Copilot ───────────────────────────────────────┐"
echo "│ File: <workspace>/.vscode/mcp.json                        │"
cat << 'EOF'
│ {
│   "servers": {
│     "memory": {
│       "type": "http",
│       "url": "http://127.0.0.1:3050/mcp"
│     }
│   }
│ }
EOF
echo "└────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─── Generic (STDIO via 1mcp) ─────────────────────────────┐"
echo "│ Any MCP-compatible client can connect via HTTP:          │"
echo "│   URL: http://127.0.0.1:3050/mcp                         │"
echo "│   Transport: HTTP/SSE                                    │"
echo "│   Tools: 45 across 7 servers                             │"
echo "└────────────────────────────────────────────────────────────┘"
SHOWSCRIPT
chmod +x "$INSTALL_DIR/show-mcp-config.sh"

# ── Summary ───────────────────────────────────────────────────────

TOTAL_SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | awk '{print $1}')

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Installation Complete!                                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location:    $INSTALL_DIR ($TOTAL_SIZE)"
echo "  Qdrant:      http://127.0.0.1:6333"
if [ "${GATEWAY_HEALTHY:-false}" = "true" ]; then
    echo "  Gateway:     http://127.0.0.1:3050"
fi
echo "  Vault:       $INSTALL_DIR/vault/"
echo "  Config:      $INSTALL_DIR/config/.env"
echo "  MCP Config:  $HOME/.config/1mcp/mcp.json"
echo ""
echo "  ┌─ Connect your AI agent ──────────────────────────────┐"
echo "  │  Claude Code  → ~/.claude/mcp/memory.json            │"
echo "  │  OpenCode     → add to ~/.config/opencode/opencode   │"
echo "  │  Cursor       → <project>/.cursor/mcp.json           │"
echo "  │  VS Code      → <workspace>/.vscode/mcp.json         │"
echo "  │                                                      │"
echo "  │  Endpoint: http://127.0.0.1:3050/mcp                 │"
echo "  │  Type: http (SSE transport)                          │"
echo "  │  Tools: 45 across 7 servers                          │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
echo "  Quick config: $INSTALL_DIR/show-mcp-config.sh"
echo ""
echo "  To restart services:"
echo "    launchctl stop com.memory-server.qdrant && launchctl start com.memory-server.qdrant"
if [ "${GATEWAY_AVAILABLE:-true}" = "true" ]; then
    echo "    launchctl stop com.memory-server.gateway && launchctl start com.memory-server.gateway"
fi
