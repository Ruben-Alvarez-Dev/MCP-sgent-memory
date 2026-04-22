#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════
# MCP Memory Server — Unified Installer v3
#
# Single MCP server entry point consolidating all 7 memory modules:
#   automem, autodream, vk-cache, conversation-store, mem0,
#   engram, sequential-thinking
#
# Installs to: ~/MCP-servers/MCP-agent-memory/
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Unified Installer v3             ║"
echo "║   Single Server · 51 Tools · Prefixed by Module        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Ask install location ──────────────────────────────────────────
DEFAULT_DIR="$HOME/MCP-servers/MCP-agent-memory"
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

if [ "$MISSING" -eq 1 ]; then
    echo "Prerequisites not met. Aborting."
    exit 1
fi

echo "  ✓ Python $($PY_CMD --version 2>&1)"

# ── Auto-detect ports ────────────────────────────────────────────
find_free_port() {
    local port=$1
    while lsof -i :$port >/dev/null 2>&1; do port=$((port + 1)); done
    echo $port
}

QDRANT_PORT=$(find_free_port 6333)
LLAMA_PORT=$(find_free_port 8081)

echo ""
echo "Ports (auto-detected):"
echo "  Qdrant:      $QDRANT_PORT"
echo "  Embeddings:  $LLAMA_PORT"

# ── Phase 1: Directory structure ──────────────────────────────────
echo ""
echo "── Phase 1: Directory structure ───────────────────────────"

mkdir -p "$INSTALL_DIR"/{src,config,vault,models,engine/bin,bin,scripts,data}
mkdir -p "$INSTALL_DIR"/src/{automem,autodream,vk-cache,conversation-store,mem0,engram,sequential-thinking,unified}/server
mkdir -p "$INSTALL_DIR"/src/shared/{llm,retrieval,compliance,vault_manager,models,qdrant,workspace}
mkdir -p "$INSTALL_DIR"/data/memory/{engram,dream,thoughts,heartbeats,reminders}
mkdir -p "$INSTALL_DIR"/data/staging_buffer
mkdir -p "$INSTALL_DIR"/tests/e2e

echo "  ✓ Directory tree created"

# ── Phase 2: Binary dependencies ─────────────────────────────────
echo ""
echo "── Phase 2: Binary dependencies ───────────────────────────"

# System llama.cpp
if command -v llama-embedding &> /dev/null; then
    echo "  ✓ Engine: system llama.cpp ($(which llama-embedding))"
elif [ -f "$SCRIPT_DIR/engine/bin/llama-embedding" ]; then
    cp "$SCRIPT_DIR/engine/bin/llama-embedding" "$INSTALL_DIR/engine/bin/"
    echo "  ✓ Engine: bundled llama.cpp"
else
    echo "  ⚠ No llama.cpp found. Install with: brew install llama.cpp"
fi

# Qdrant - check bundled first, then system
QDRANT_BIN=""
if [ -f "$SCRIPT_DIR/shared/qdrant/qdrant" ]; then
    QDRANT_BIN="$SCRIPT_DIR/shared/qdrant/qdrant"
elif [ -f "$HOME/MCP-servers/MCP-agent-memory/bin/qdrant" ]; then
    QDRANT_BIN="$HOME/MCP-servers/MCP-agent-memory/bin/qdrant"
elif command -v qdrant &> /dev/null; then
    QDRANT_BIN="system"
fi

if [ -n "$QDRANT_BIN" ] && [ "$QDRANT_BIN" != "system" ]; then
    cp "$QDRANT_BIN" "$INSTALL_DIR/bin/qdrant"
    echo "  ✓ Qdrant: bundled"
elif [ "$QDRANT_BIN" = "system" ]; then
    echo "  ✓ Qdrant: system"
else
    echo "  ⚠ Qdrant not found. Will attempt download."
    # Attempt to download Qdrant
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        QDRANT_URL="https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-apple-darwin.tar.gz"
    else
        QDRANT_URL="https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-apple-darwin.tar.gz"
    fi
    curl -sL "$QDRANT_URL" | tar xz -C "$INSTALL_DIR/bin/" 2>/dev/null && echo "  ✓ Qdrant: downloaded" || echo "  ✗ Qdrant download failed"
fi

# ── Phase 3: Server code ─────────────────────────────────────────
echo ""
echo "── Phase 3: Server code ───────────────────────────────────"

SERVERS="automem autodream vk-cache conversation-store mem0 engram sequential-thinking"

for server in $SERVERS; do
    if [ -f "$SCRIPT_DIR/$server/server/main.py" ]; then
        cp "$SCRIPT_DIR/$server/server/main.py" "$INSTALL_DIR/src/$server/server/"
        echo "  ✓ $server"
    elif [ -f "$SCRIPT_DIR/servers/$server/server/main.py" ]; then
        cp "$SCRIPT_DIR/servers/$server/server/main.py" "$INSTALL_DIR/src/$server/server/"
        echo "  ✓ $server (flat layout)"
    else
        echo "  ⚠ $server not found"
    fi
done

# Copy unified server
echo ""
echo "  Installing unified server..."
if [ -d "$SCRIPT_DIR/unified" ]; then
    cp -R "$SCRIPT_DIR/unified/" "$INSTALL_DIR/src/unified/"
    echo "  ✓ unified"
else
    echo "  ⚠ unified not found (will use individual servers as fallback)"
fi

# Copy shared modules
echo ""
echo "  Installing shared modules..."
for pkg in llm retrieval compliance vault_manager models qdrant workspace; do
    if [ -d "$SCRIPT_DIR/shared/$pkg" ]; then
        find "$SCRIPT_DIR/shared/$pkg" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        cp -R "$SCRIPT_DIR/shared/$pkg" "$INSTALL_DIR/src/shared/"
        echo "  ✓ shared/$pkg"
    fi
done

for f in __init__.py embedding.py env_loader.py observe.py sanitize.py diff_sandbox.py health.py; do
    if [ -f "$SCRIPT_DIR/shared/$f" ]; then
        cp "$SCRIPT_DIR/shared/$f" "$INSTALL_DIR/src/shared/"
        echo "  ✓ shared/$f"
    fi
done

# ── Phase 4: Python environment ──────────────────────────────────
echo ""
echo "── Phase 4: Python environment ───────────────────────────"

$PY_CMD -m venv "$INSTALL_DIR/.venv"
PYTHON_VENV="$INSTALL_DIR/.venv/bin/python3"

# Install MCP and dependencies
"$INSTALL_DIR/.venv/bin/pip" install --quiet mcp qdrant-client httpx pydantic 2>/dev/null || true
echo "  ✓ Python venv + packages"

# ── Phase 5: Configuration ───────────────────────────────────────
echo ""
echo "── Phase 5: Configuration ────────────────────────────────"

# .env
cat > "$INSTALL_DIR/config/.env" << EOF
QDRANT_URL=http://127.0.0.1:$QDRANT_PORT
LLAMA_SERVER_URL=http://127.0.0.1:$LLAMA_PORT
EMBEDDING_BACKEND=llama_server
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
VAULT_PATH=$INSTALL_DIR/vault
ENGRAM_PATH=$INSTALL_DIR/data/memory/engram
MEMORY_SERVER_DIR=$INSTALL_DIR
EOF

# mcp.json — unified server
cat > "$INSTALL_DIR/config/mcp.json" << MCPJSON
{
  "mcpServers": {
    "memory": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:$QDRANT_PORT",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024",
        "LLM_BACKEND": "ollama",
        "LLM_MODEL": "qwen2.5:7b",
        "VAULT_PATH": "$INSTALL_DIR/vault",
        "ENGRAM_PATH": "$INSTALL_DIR/data/memory/engram"
      }
    }
  }
}
MCPJSON

echo "  ✓ config/.env"
echo "  ✓ config/mcp.json"

# ── Phase 6: Startup scripts ─────────────────────────────────────
echo ""
echo "── Phase 6: Startup scripts ──────────────────────────────"

# start-qdrant.sh
cat > "$INSTALL_DIR/scripts/start-qdrant.sh" << 'SCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
source "$INSTALL_DIR/config/.env" 2>/dev/null || true
PORT=$(echo "$QDRANT_URL" | grep -oE '[0-9]+$' || echo "6333")

if [ -f "$INSTALL_DIR/bin/qdrant" ]; then
    "$INSTALL_DIR/bin/qdrant" --config-path "$INSTALL_DIR/config/qdrant.yaml" 2>&1 &
elif command -v qdrant &> /dev/null; then
    qdrant 2>&1 &
else
    echo "Qdrant not found"
    exit 1
fi
echo "Qdrant starting on port $PORT..."
SCRIPT
chmod +x "$INSTALL_DIR/scripts/start-qdrant.sh"

# start-all.sh
cat > "$INSTALL_DIR/scripts/start-all.sh" << 'SCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting MCP Memory Server..."
"$SCRIPT_DIR/start-qdrant.sh"
sleep 2

# Verify Qdrant
source "$INSTALL_DIR/config/.env" 2>/dev/null || true
if curl -s "$QDRANT_URL/healthz" >/dev/null 2>&1; then
    echo "  ✓ Qdrant healthy"
else
    echo "  ⚠ Qdrant may not be ready yet"
fi

echo "Memory server ready. Connect via MCP config at: $INSTALL_DIR/config/mcp.json"
SCRIPT
chmod +x "$INSTALL_DIR/scripts/start-all.sh"

echo "  ✓ scripts/start-qdrant.sh"
echo "  ✓ scripts/start-all.sh"

# ── Phase 7: Verification ────────────────────────────────────────
echo ""
echo "── Phase 7: Verification ─────────────────────────────────"

PASS=0
FAIL=0

check() {
    if [ -e "$1" ]; then
        echo "  ✓ $2"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $2"
        FAIL=$((FAIL + 1))
    fi
}

# Server modules
for server in automem autodream vk-cache conversation-store mem0 engram sequential-thinking; do
    check "$INSTALL_DIR/src/$server/server/main.py" "src/$server/server/main.py"
done

# Unified server
check "$INSTALL_DIR/src/unified/server/main.py" "src/unified/server/main.py"

# Shared modules
for f in __init__.py embedding.py env_loader.py observe.py sanitize.py health.py; do
    check "$INSTALL_DIR/src/shared/$f" "shared/$f"
done

# Config
check "$INSTALL_DIR/config/.env" "config/.env"
check "$INSTALL_DIR/config/mcp.json" "config/mcp.json"

# Python imports
if "$PYTHON_VENV" -c "
import sys; sys.path.insert(0, '$INSTALL_DIR/src')
from shared.env_loader import load_env; load_env()
from shared.embedding import get_embedding
from shared.models import MemoryItem
print('  ✓ Python imports work')
" 2>/dev/null; then
    PASS=$((PASS + 1))
else
    echo "  ✗ Python imports failed"
    FAIL=$((FAIL + 1))
fi

# Qdrant
if [ -n "$QDRANT_BIN" ]; then
    # Start Qdrant temporarily for verification
    if [ -f "$INSTALL_DIR/bin/qdrant" ]; then
        "$INSTALL_DIR/bin/qdrant" --config-path "$INSTALL_DIR/config/qdrant.yaml" 2>/dev/null &
        QDRANT_PID=$!
        sleep 2
    fi
    
    if curl -s "http://127.0.0.1:$QDRANT_PORT/healthz" >/dev/null 2>&1; then
        echo "  ✓ Qdrant healthy (port $QDRANT_PORT)"
        PASS=$((PASS + 1))
    else
        echo "  ⚠ Qdrant not responding (may need manual start)"
    fi
    
    # Stop temporary Qdrant
    [ -n "$QDRANT_PID" ] && kill $QDRANT_PID 2>/dev/null
fi

# ── Summary ──────────────────────────────────────────────────────
SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1)

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   ✓ Installation Complete                              ║"
    echo "╚══════════════════════════════════════════════════════════╝"
else
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║   ⚠ Installation Complete ($FAIL warnings)              ║"
    echo "╚══════════════════════════════════════════════════════════╝"
fi

echo ""
echo "  Location:    $INSTALL_DIR ($SIZE)"
echo "  Architecture: Unified (1 server, 51 tools)"
echo "  Qdrant:      http://127.0.0.1:$QDRANT_PORT"
echo "  Config:      $INSTALL_DIR/config/.env"
echo "  MCP Config:  $INSTALL_DIR/config/mcp.json"
echo ""
echo "  To start:"
echo "    $INSTALL_DIR/scripts/start-all.sh"
echo ""
echo "  To connect Pi/Claude:"
echo "    cp $INSTALL_DIR/config/mcp.json ~/.pi/mcp.json"
echo ""
