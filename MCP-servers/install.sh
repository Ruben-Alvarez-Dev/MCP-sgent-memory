#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════
# MCP Memory Server — Self-Contained Installer
#
# Installs to: ~/MCP-servers/MCP-memory-server/
#
# Layout (mirrors dev structure):
#   INSTALL_DIR/
#   ├── src/                    ← All server code (same layout as dev)
#   │   ├── automem/server/main.py
#   │   ├── shared/embedding.py
#   │   └── ...
#   ├── engine/                 ← llama.cpp binaries (from bundled or system)
#   ├── models/                 ← .gguf embedding models
#   ├── bin/                    ← Qdrant binary
#   ├── config/                 ← .env + mcp.json
#   ├── vault/                  ← Obsidian vault
#   ├── .venv/                  ← Python environment
#   └── scripts/                ← Startup scripts
#
# No Docker. No Homebrew deps. Self-contained.
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Installer v2                     ║"
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

# ══════════════════════════════════════════════════════════════════
# PHASE 1: Source resolution — find engine, models, qdrant
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 1: Resolving binary dependencies ───────────────────"
echo ""

# --- Engine (llama.cpp) ---
ENGINE_SRC=""
# 1. Bundled in installer package
if [ -f "$SCRIPT_DIR/engine/bin/llama-embedding" ]; then
    ENGINE_SRC="$SCRIPT_DIR/engine"
    echo "  ✓ Engine: bundled in installer"
# 2. Existing production install
elif [ -f "$HOME/MCP-servers/MCP-memory-server/bin/engine/bin/llama-embedding" ]; then
    ENGINE_SRC="$HOME/MCP-servers/MCP-memory-server/bin/engine"
    echo "  ✓ Engine: existing production install"
# 3. System llama.cpp (Homebrew)
elif [ -x "$(command -v llama-embedding 2>/dev/null)" ]; then
    ENGINE_SRC="system"
    echo "  ✓ Engine: system llama.cpp ($(command -v llama-embedding))"
fi

if [ -z "$ENGINE_SRC" ]; then
    echo "  ⚠ No llama.cpp engine found. Embeddings will use subprocess fallback."
fi

# --- Models ---
MODEL_SRC=""
# 1. Bundled
if ls "$SCRIPT_DIR/models/"*.gguf &>/dev/null; then
    MODEL_SRC="$SCRIPT_DIR/models"
    echo "  ✓ Models: bundled ($(ls "$SCRIPT_DIR/models/"*.gguf | head -1 | xargs basename))"
# 2. Existing production
elif [ -f "$HOME/MCP-servers/MCP-memory-server/bin/models/bge-m3-Q4_K_M.gguf" ]; then
    MODEL_SRC="$HOME/MCP-servers/MCP-memory-server/bin/models"
    echo "  ✓ Models: existing production install"
# 3. Check common locations
elif [ -f "$HOME/.cache/lm-studio/models/bge-m3-Q4_K_M.gguf" ]; then
    MODEL_SRC="lmstudio"
    echo "  ✓ Models: LM Studio cache"
fi

if [ -z "$MODEL_SRC" ]; then
    echo "  ⚠ No .gguf models found. Will attempt download."
fi

# --- Qdrant ---
QDRANT_BIN=""
# 1. Bundled
if [ -f "$SCRIPT_DIR/shared/qdrant/qdrant" ]; then
    QDRANT_BIN="$SCRIPT_DIR/shared/qdrant/qdrant"
    echo "  ✓ Qdrant: bundled"
# 2. Existing production
elif [ -f "$HOME/MCP-servers/MCP-memory-server/bin/qdrant" ]; then
    QDRANT_BIN="$HOME/MCP-servers/MCP-memory-server/bin/qdrant"
    echo "  ✓ Qdrant: existing production"
# 3. System
elif command -v qdrant &>/dev/null; then
    QDRANT_BIN="system"
    echo "  ✓ Qdrant: system ($(command -v qdrant))"
fi

if [ -z "$QDRANT_BIN" ]; then
    echo "  ⚠ Qdrant binary not found. Will attempt download."
fi

# ══════════════════════════════════════════════════════════════════
# PHASE 2: Create directory structure
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 2: Creating directory structure ─────────────────────"
echo ""

# Servers go into src/ — SAME layout as dev (servers are siblings of shared/)
mkdir -p "$INSTALL_DIR"/src/{automem,autodream,vk-cache,conversation-store,mem0,engram,sequential-thinking,,}/server
mkdir -p "$INSTALL_DIR"/src/shared/{llm,retrieval,compliance,vault_manager,models,qdrant}
mkdir -p "$INSTALL_DIR"/engine/{bin,lib}
mkdir -p "$INSTALL_DIR"/models
mkdir -p "$INSTALL_DIR"/bin
mkdir -p "$INSTALL_DIR"/config
mkdir -p "$INSTALL_DIR"/scripts
mkdir -p "$INSTALL_DIR"/tests/e2e
mkdir -p "$INSTALL_DIR"/vault/{Inbox,"Decisiones","Conocimiento",Episodios,Log_Global,Entidades,Personas,Templates}
mkdir -p "$INSTALL_DIR"/vault/.system/{locks,backups,trash/{human-deleted,system-deleted},orphaned}

echo "  ✓ Directory tree created"

# ══════════════════════════════════════════════════════════════════
# PHASE 3: Install binaries
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 3: Installing binaries ──────────────────────────────"
echo ""

# --- Engine ---
if [ -n "$ENGINE_SRC" ] && [ "$ENGINE_SRC" != "system" ]; then
    echo "Installing llama.cpp engine..."
    cp -R "$ENGINE_SRC/bin/"* "$INSTALL_DIR/engine/bin/" 2>/dev/null || true
    cp -R "$ENGINE_SRC/lib/"* "$INSTALL_DIR/engine/lib/" 2>/dev/null || true
    ENGINE_COUNT=$(ls "$INSTALL_DIR/engine/bin/" 2>/dev/null | wc -l | tr -d ' ')
    echo "  ✓ $ENGINE_COUNT binaries, $(ls "$INSTALL_DIR/engine/lib/" 2>/dev/null | wc -l | tr -d ' ') libraries"
elif [ "$ENGINE_SRC" = "system" ]; then
    echo "  ℹ Using system llama.cpp — no bundling needed"
    echo "  → embedding.py will auto-detect $(command -v llama-embedding)"
fi

# Re-sign binaries (required after copy on macOS)
if [ "$OS" = "Darwin" ] && [ -d "$INSTALL_DIR/engine/bin" ]; then
    echo "  → Re-signing binaries..."
    for bin in "$INSTALL_DIR/engine/bin/"*; do
        [ -f "$bin" ] && codesign --force --sign - "$bin" 2>/dev/null || true
    done
    for lib in "$INSTALL_DIR/engine/lib/"*.dylib; do
        [ -f "$lib" ] && codesign --force --sign - "$lib" 2>/dev/null || true
    done
    echo "  ✓ Binaries signed"
fi

# --- Models ---
if [ -n "$MODEL_SRC" ] && [ "$MODEL_SRC" != "lmstudio" ]; then
    echo "Installing embedding models..."
    cp "$MODEL_SRC/"*.gguf "$INSTALL_DIR/models/"
    MODEL_SIZE=$(du -sh "$INSTALL_DIR/models/"*.gguf | head -1 | awk '{print $1}')
    MODEL_COUNT=$(ls "$INSTALL_DIR/models/"*.gguf | wc -l | tr -d ' ')
    echo "  ✓ $MODEL_COUNT models ($MODEL_SIZE)"
elif [ "$MODEL_SRC" = "lmstudio" ]; then
    echo "  ℹ Using LM Studio cache models"
else
    # Try to download BGE-M3
    echo "  → Downloading BGE-M3 model (this may take a while)..."
    if command -v pip &>/dev/null || command -v pip3 &>/dev/null; then
        PIP_CMD=$(command -v pip3 2>/dev/null || command -v pip 2>/dev/null)
        $PIP_CMD download --dest "$INSTALL_DIR/models" \
            "huggingface_hub" 2>/dev/null || true
    fi
    # Use huggingface-cli or wget
    if command -v wget &>/dev/null; then
        wget -q --show-progress -O "$INSTALL_DIR/models/bge-m3-Q4_K_M.gguf" \
            "https://huggingface.co/ilsilfverskiold/bge-m3-gguf/resolve/main/bge-m3-Q4_K_M.gguf" 2>&1 || {
            echo "  ⚠ Download failed. Place .gguf model manually in $INSTALL_DIR/models/"
        }
    elif command -v curl &>/dev/null; then
        curl -L -o "$INSTALL_DIR/models/bge-m3-Q4_K_M.gguf" \
            "https://huggingface.co/ilsilfverskiold/bge-m3-gguf/resolve/main/bge-m3-Q4_K_M.gguf" 2>&1 || {
            echo "  ⚠ Download failed. Place .gguf model manually in $INSTALL_DIR/models/"
        }
    fi
fi

# --- Qdrant ---
if [ -n "$QDRANT_BIN" ] && [ "$QDRANT_BIN" != "system" ]; then
    cp "$QDRANT_BIN" "$INSTALL_DIR/bin/qdrant"
    chmod +x "$INSTALL_DIR/bin/qdrant"
    if [ "$OS" = "Darwin" ]; then
        codesign --force --sign - "$INSTALL_DIR/bin/qdrant" 2>/dev/null || true
    fi
    echo "  ✓ Qdrant binary installed"
elif [ "$QDRANT_BIN" = "system" ]; then
    echo "  ℹ Using system Qdrant"
fi

# Qdrant config (always copy)
if [ -f "$SCRIPT_DIR/shared/qdrant/config.yaml" ]; then
    cp "$SCRIPT_DIR/shared/qdrant/config.yaml" "$INSTALL_DIR/src/shared/qdrant/"
fi

# ══════════════════════════════════════════════════════════════════
# PHASE 4: Install server code (src/ layout = dev layout)
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 4: Installing server code ───────────────────────────"
echo ""

# Source servers: look in both dev layout ($SCRIPT_DIR/$server/) 
# and flat layout ($SCRIPT_DIR/servers/$server/)
SERVERS="automem autodream vk-cache conversation-store mem0 engram sequential-thinking  "

for server in $SERVERS; do
    # Try dev layout first (current structure: MCP-servers/$server/)
    if [ -f "$SCRIPT_DIR/$server/server/main.py" ]; then
        cp "$SCRIPT_DIR/$server/server/main.py" "$INSTALL_DIR/src/$server/server/"
        echo "  ✓ $server"
    # Try flat layout (build package: servers/$server/)
    elif [ -f "$SCRIPT_DIR/servers/$server/server/main.py" ]; then
        cp "$SCRIPT_DIR/servers/$server/server/main.py" "$INSTALL_DIR/src/$server/server/"
        echo "  ✓ $server (from flat layout)"
    else
        echo "  ⚠ $server not found"
    fi
done

# Copy shared modules (full packages)
echo ""
echo "Installing shared modules..."
for pkg in llm retrieval compliance vault_manager models qdrant; do
    if [ -d "$SCRIPT_DIR/shared/$pkg" ]; then
        # Remove any .pyc or __pycache__ before copy
        find "$SCRIPT_DIR/shared/$pkg" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        cp -R "$SCRIPT_DIR/shared/$pkg" "$INSTALL_DIR/src/shared/"
        echo "  ✓ shared/$pkg"
    fi
done

# Copy individual shared files
for f in embedding.py __init__.py env_loader.py observe.py; do
    if [ -f "$SCRIPT_DIR/shared/$f" ]; then
        cp "$SCRIPT_DIR/shared/$f" "$INSTALL_DIR/src/shared/"
        echo "  ✓ shared/$f"
    fi
done

# Copy vault templates
if [ -d "$SCRIPT_DIR/vault/Templates" ]; then
    cp "$SCRIPT_DIR/vault/Templates/"* "$INSTALL_DIR/vault/Templates/" 2>/dev/null || true
    echo "  ✓ vault templates"
fi

# Copy tests
if [ -d "$SCRIPT_DIR/tests" ]; then
    cp "$SCRIPT_DIR/tests/"*.py "$INSTALL_DIR/tests/" 2>/dev/null || true
    cp -R "$SCRIPT_DIR/tests/e2e" "$INSTALL_DIR/tests/" 2>/dev/null || true
    echo "  ✓ tests"
fi

# ══════════════════════════════════════════════════════════════════
# PHASE 5: Python environment
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 5: Python environment ───────────────────────────────"
echo ""

$PY_CMD -m venv "$INSTALL_DIR/.venv"
source "$INSTALL_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet mcp pydantic httpx pyyaml
echo "  ✓ Python venv + packages"

PYTHON_VENV="$INSTALL_DIR/.venv/bin/python3"

# ══════════════════════════════════════════════════════════════════
# PHASE 6: Configuration
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 6: Configuration ────────────────────────────────────"
echo ""

# Detect LLM backend
LLM_BACKEND="ollama"
LLM_MODEL="qwen2.5:7b"
if [ -f "$HOME/MCP-servers/MCP-memory-server/config/.env" ]; then
    EXISTING_BACKEND=$(grep "^LLM_BACKEND=" "$HOME/MCP-servers/MCP-memory-server/config/.env" 2>/dev/null | cut -d= -f2)
    EXISTING_MODEL=$(grep "^LLM_MODEL=" "$HOME/MCP-servers/MCP-memory-server/config/.env" 2>/dev/null | cut -d= -f2)
    [ -n "$EXISTING_BACKEND" ] && LLM_BACKEND="$EXISTING_BACKEND"
    [ -n "$EXISTING_MODEL" ] && LLM_MODEL="$EXISTING_MODEL"
fi

# Detect embedding dimension based on available model
EMBEDDING_DIM=384  # MiniLM default
if ls "$INSTALL_DIR/models/"*bge*m3* &>/dev/null; then
    EMBEDDING_DIM=1024
elif ls "$INSTALL_DIR/models/"*nomic* &>/dev/null; then
    EMBEDDING_DIM=768
fi

cat > "$INSTALL_DIR/config/.env" << EOF
# MCP Memory Server — Configuration
# Generated by installer on $(date '+%Y-%m-%d %H:%M:%S')

# ── Paths ──────────────────────────────────────────────────────────
MEMORY_SERVER_DIR=$INSTALL_DIR
PYTHONPATH=$INSTALL_DIR/src

# ── Shared Infrastructure ──────────────────────────────────────────
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=automem
CONV_COLLECTION=conversations
MEM0_COLLECTION=mem0_memories

# ── Embedding ──────────────────────────────────────────────────────
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=$EMBEDDING_DIM

# ── LLM Backend (agnostic) ─────────────────────────────────────────
LLM_BACKEND=$LLM_BACKEND
LLM_MODEL=$LLM_MODEL

# ── Ollama ─────────────────────────────────────────────────────────
OLLAMA_URL=http://127.0.0.1:11434

# ── Vault ──────────────────────────────────────────────────────────
VAULT_PATH=$INSTALL_DIR/vault

# ── Runtime Paths ──────────────────────────────────────────────────
DREAM_PATH=\$HOME/.memory/dream
ENGRAM_PATH=\$HOME/.memory/engram
AUTOMEM_JSONL=\$HOME/.memory/raw_events.jsonl

# ── vk-cache ───────────────────────────────────────────────────────
VK_MIN_SCORE=0.3
VK_MAX_ITEMS=8
VK_MAX_TOKENS=8000

# ── AutoDream schedules ────────────────────────────────────────────
DREAM_PROMOTE_L1=10
DREAM_PROMOTE_L2=3600
DREAM_PROMOTE_L3=86400
DREAM_PROMOTE_L4=604800

# ── Python ─────────────────────────────────────────────────────────
PYTHON_BIN=$PYTHON_VENV
EOF

# ── mcp.json for 1MCP gateway ─────────────────────────────────────

# All paths use src/ layout — servers and shared are siblings
cat > "$INSTALL_DIR/config/mcp.json" << EOF
{
  "mcpServers": {
    "automem": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/automem/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "$EMBEDDING_DIM"
      },
      "tags": ["memory", "ingest"],
      "disabled": false
    },
    "autodream": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/autodream/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
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
      "args": ["-u", "$INSTALL_DIR/src/vk-cache/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
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
      "args": ["-u", "$INSTALL_DIR/src/conversation-store/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333"
      },
      "tags": ["memory", "conversations"],
      "disabled": false
    },
    "mem0": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/mem0/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333"
      },
      "tags": ["memory", "semantic"],
      "disabled": false
    },
    "engram": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/engram/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "VAULT_PATH": "$INSTALL_DIR/vault"
      },
      "tags": ["memory", "decisions", "vault"],
      "disabled": false
    },
    "sequential-thinking": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src/sequential-thinking/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR"
      },
      "tags": ["reasoning", "planning"],
      "disabled": false
    },
    "": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src//server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333"
      },
      "tags": ["memory", "facade"],
      "disabled": false
    },
    "": {
      "command": "$PYTHON_VENV",
      "args": ["-u", "$INSTALL_DIR/src//server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR"
      },
      "tags": ["docs", "proxy"],
      "disabled": false
    }
  }
}
EOF

echo "  ✓ config/.env"
echo "  ✓ config/mcp.json"

# ══════════════════════════════════════════════════════════════════
# PHASE 7: Startup scripts
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 7: Startup scripts ─────────────────────────────────"
echo ""

# Qdrant start script
cat > "$INSTALL_DIR/scripts/start-qdrant.sh" << 'QSCRIPT'
#!/bin/bash
ulimit -n 10240
export MALLOC_CONF="background_thread:false,narenas:1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$INSTALL_DIR/src/shared/qdrant"
mkdir -p data snapshots

QDRANT_BIN=""
if [ -f "$INSTALL_DIR/bin/qdrant" ]; then
    QDRANT_BIN="$INSTALL_DIR/bin/qdrant"
elif command -v qdrant &>/dev/null; then
    QDRANT_BIN="qdrant"
else
    echo "ERROR: qdrant binary not found"
    exit 1
fi
exec "$QDRANT_BIN" --config-path config.yaml
QSCRIPT
chmod +x "$INSTALL_DIR/scripts/start-qdrant.sh"

# Embedding server start script
cat > "$INSTALL_DIR/scripts/start-embedding-server.sh" << ESCRIPT
#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
ENGINE_DIR="$INSTALL_DIR/engine"
MODEL_DIR="$INSTALL_DIR/models"
PORT="\${LLAMA_SERVER_PORT:-8080}"
HOST="\${LLAMA_SERVER_HOST:-127.0.0.1}"
LOG_FILE="\${LLAMA_SERVER_LOG:-$INSTALL_DIR/logs/embedding-server.log}"
PID_FILE="$INSTALL_DIR/logs/embedding-server.pid"

mkdir -p "$INSTALL_DIR/logs"

# Find model
MODEL=""
for candidate in \\
    "\$MODEL_DIR/bge-m3-Q4_K_M.gguf" \\
    "\$MODEL_DIR/bge-m3"*".gguf" \\
    "\$MODEL_DIR/"*.gguf; do
    if [ -f "\$candidate" ]; then
        MODEL="\$candidate"
        break
    fi
done

if [ -z "\$MODEL" ]; then
    echo "ERROR: No .gguf model found in \$MODEL_DIR" >&2
    exit 1
fi

# Find binary
SERVER_BIN=""
for path in \\
    "\$ENGINE_DIR/bin/llama-server" \\
    "\$(which llama-server 2>/dev/null)"; do
    if [ -x "\$path" ]; then
        SERVER_BIN="\$path"
        break
    fi
done

if [ -z "\$SERVER_BIN" ]; then
    echo "ERROR: llama-server binary not found" >&2
    exit 1
fi

# Check if already running
if curl -sf "http://\$HOST:\$PORT/health" > /dev/null 2>&1; then
    echo "✅ Embedding server already running on \$HOST:\$PORT"
    exit 0
fi

# Kill stale
if [ -f "\$PID_FILE" ]; then
    OLD_PID=\$(cat "\$PID_FILE")
    kill -0 "\$OLD_PID" 2>/dev/null && kill "\$OLD_PID" 2>/dev/null || true
    rm -f "\$PID_FILE"
fi

echo "🚀 Starting embedding server..."
echo "   Binary: \$SERVER_BIN"
echo "   Model:  \$MODEL"
echo "   Port:   \$PORT"

export DYLD_LIBRARY_PATH="\$ENGINE_DIR/lib\${DYLD_LIBRARY_PATH:+:\$DYLD_LIBRARY_PATH}"
export LD_LIBRARY_PATH="\$ENGINE_DIR/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"

nohup "\$SERVER_BIN" \\
    -m "\$MODEL" \\
    --embedding \\
    --port "\$PORT" \\
    --host "\$HOST" \\
    -c 512 -t 4 --mlock \\
    > "\$LOG_FILE" 2>&1 &

echo \$! > "\$PID_FILE"

for i in \$(seq 1 60); do
    curl -sf "http://\$HOST:\$PORT/health" > /dev/null 2>&1 && \\
        echo "✅ Ready (PID \$(cat \$PID_FILE))" && exit 0
    sleep 0.5
done

echo "ERROR: Failed to start within 30s" >&2
rm -f "\$PID_FILE"
exit 1
ESCRIPT
chmod +x "$INSTALL_DIR/scripts/start-embedding-server.sh"

# All-in-one launcher
cat > "$INSTALL_DIR/scripts/start-all.sh" << 'ALLSCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

echo "🧠 Starting MCP Memory Server ecosystem..."

# 1. Qdrant
if ! curl -s http://127.0.0.1:6333/health > /dev/null 2>&1; then
    echo "📦 Starting Qdrant..."
    "$SCRIPT_DIR/start-qdrant.sh" &
    sleep 3
fi

# 2. Embedding server
if ! curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
    echo "🚀 Starting embedding server..."
    "$SCRIPT_DIR/start-embedding-server.sh"
fi

export EMBEDDING_BACKEND="llama_server"
echo "✨ Ecosystem ready."
ALLSCRIPT
chmod +x "$INSTALL_DIR/scripts/start-all.sh"

# Gateway start script
cat > "$INSTALL_DIR/scripts/start-gateway.sh" << 'GWSCRIPT'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

export ONE_MCP_CONFIG="$INSTALL_DIR/config/mcp.json"
export MEMORY_SERVER_DIR="$INSTALL_DIR"

# Start embedding server first
"$SCRIPT_DIR/start-embedding-server.sh" 2>/dev/null || true
export EMBEDDING_BACKEND=llama_server

if command -v 1mcp &>/dev/null; then
    exec 1mcp serve --port 3050 --enable-config-reload false
else
    echo "ERROR: 1mcp not installed. Run: npm install -g @1mcp/agent"
    exit 1
fi
GWSCRIPT
chmod +x "$INSTALL_DIR/scripts/start-gateway.sh"

echo "  ✓ start-qdrant.sh"
echo "  ✓ start-embedding-server.sh"
echo "  ✓ start-all.sh"
echo "  ✓ start-gateway.sh"

# ══════════════════════════════════════════════════════════════════
# PHASE 8: launchd services (macOS)
# ══════════════════════════════════════════════════════════════════

if [ "$OS" = "Darwin" ]; then
    echo ""
    echo "── Phase 8: launchd services ─────────────────────────────────"
    echo ""

    mkdir -p "$HOME/.memory"/{dream,engram,heartbeats,reminders,thoughts}

    # --- Qdrant ---
    cat > "$HOME/Library/LaunchAgents/com.memory-server.qdrant.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.qdrant</string>
    <key>ProgramArguments</key><array>
        <string>$INSTALL_DIR/scripts/start-qdrant.sh</string>
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
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

    # Wait for Qdrant
    echo "  → Waiting for Qdrant..."
    sleep 3

    # Create collections
    if curl -s http://127.0.0.1:6333/health &>/dev/null; then
        echo "  ✓ Qdrant running"
        for col in automem conversations mem0_memories; do
            curl -s -X DELETE "http://127.0.0.1:6333/collections/$col" &>/dev/null || true
            curl -s -X PUT "http://127.0.0.1:6333/collections/$col" \
                -H "Content-Type: application/json" \
                -d "{\"vectors\":{\"size\":$EMBEDDING_DIM,\"distance\":\"Cosine\"},\"sparse_vectors\":{\"text\":{\"index\":{\"type\":\"bm25\"}}}}" \
                &>/dev/null && echo "  ✓ Collection $col ($EMBEDDING_DIMd + BM25)"
        done
    else
        echo "  ⚠ Qdrant not responding yet"
    fi

    # --- Gateway (if Node.js available) ---
    GATEWAY_AVAILABLE=false
    if command -v node &>/dev/null && command -v 1mcp &>/dev/null; then
        GATEWAY_AVAILABLE=true
        GATEWAY_EXEC=$(command -v node)
        GATEWAY_BIN=$(command -v 1mcp)
        NODE_DIR=$(dirname "$GATEWAY_EXEC")
        BIN_DIR=$(dirname "$GATEWAY_BIN")

        cat > "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" << GWPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.memory-server.gateway</string>
    <key>ProgramArguments</key><array>
        <string>$GATEWAY_EXEC</string>
        <string>$GATEWAY_BIN</string>
        <string>serve</string>
        <string>--port</string><string>3050</string>
        <string>--enable-config-reload</string><string>false</string>
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$HOME/.memory/gateway.log</string>
    <key>StandardErrorPath</key><string>$HOME/.memory/gateway-error.log</string>
    <key>EnvironmentVariables</key><dict>
        <key>ONE_MCP_CONFIG</key><string>$INSTALL_DIR/config/mcp.json</string>
        <key>PATH</key><string>$BIN_DIR:$NODE_DIR:/usr/bin:/usr/local/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
GWPLIST

        # Copy mcp.json to global config
        mkdir -p "$HOME/.config/1mcp"
        cp "$INSTALL_DIR/config/mcp.json" "$HOME/.config/1mcp/mcp.json"

        launchctl unload "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist" 2>/dev/null || true
        launchctl load "$HOME/Library/LaunchAgents/com.memory-server.gateway.plist"
        echo "  ✓ Gateway service installed (port 3050)"
    else
        echo "  ⚠ Gateway skipped (install Node.js 18+ and run: npm install -g @1mcp/agent)"
    fi
fi

# ══════════════════════════════════════════════════════════════════
# PHASE 9: Verification
# ══════════════════════════════════════════════════════════════════

echo ""
echo "── Phase 9: Verification ─────────────────────────────────────"
echo ""

ERRORS=0

# Check directory structure
for dir in src/shared src/automem/server src/autodream/server src/vk-cache/server \
           src/conversation-store/server src/mem0/server src/engram/server \
           src/sequential-thinking/server src//server src//server \
           config vault models engine/bin scripts; do
    if [ -d "$INSTALL_DIR/$dir" ]; then
        echo "  ✓ $dir/"
    else
        echo "  ✗ $dir/ MISSING"
        ERRORS=$((ERRORS+1))
    fi
done

# Check critical files
for f in src/shared/__init__.py src/shared/embedding.py src/shared/env_loader.py \
         config/.env config/mcp.json; do
    if [ -f "$INSTALL_DIR/$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ $f MISSING"
        ERRORS=$((ERRORS+1))
    fi
done

# Check Python can import shared module
cd "$INSTALL_DIR"
if PYTHONPATH="$INSTALL_DIR/src" "$PYTHON_VENV" -c "
from shared.env_loader import load_env
print('  ✓ Python imports work')
" 2>/dev/null; then
    :
else
    echo "  ✗ Python import FAILED"
    ERRORS=$((ERRORS+1))
fi

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════

TOTAL_SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | awk '{print $1}')

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
if [ $ERRORS -eq 0 ]; then
    echo "║   ✅ Installation Complete!                              ║"
else
    echo "║   ⚠️  Installation Complete ($ERRORS warnings)             ║"
fi
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location:    $INSTALL_DIR ($TOTAL_SIZE)"
echo "  Layout:      src/ (servers + shared are siblings)"
echo "  Qdrant:      http://127.0.0.1:6333"
if [ "$GATEWAY_AVAILABLE" = "true" ]; then
    echo "  Gateway:     http://127.0.0.1:3050"
fi
echo "  Vault:       $INSTALL_DIR/vault/"
echo "  Config:      $INSTALL_DIR/config/.env"
echo ""
echo "  Services:"
echo "    launchctl list | grep memory-server"
echo ""
echo "  Connect agents:"
echo "    URL:  http://127.0.0.1:3050/mcp"
echo "    Type: http (SSE transport)"
echo ""
echo "  Manual start:"
echo "    $INSTALL_DIR/scripts/start-all.sh"
