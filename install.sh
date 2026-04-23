#!/bin/bash
# MCP-agent-memory — One-liner installer
# Usage: curl -fsSL <url>/install.sh | bash
# Or:    bash install.sh [install_dir]
set -euo pipefail

INSTALL_DIR="${1:-$HOME/MCP-servers/MCP-agent-memory}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Auto-bootstrap (curl | bash) ──
if [ ! -f "$SCRIPT_DIR/src/unified/server/main.py" ]; then
    REPO_URL="https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory.git"
    TMPDIR=$(mktemp -d -t mcp-mem.XXXXXX)
    echo "⬇  Downloading MCP-agent-memory..."
    git clone --depth 1 "$REPO_URL" "$TMPDIR/repo" 2>/dev/null
    bash "$TMPDIR/repo/install.sh" "$@"
    rm -rf "$TMPDIR"
    exit $?
fi

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║   MCP-agent-memory — Installer                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# ── 1. Python venv ──
echo "1/5 Creating virtual environment..."
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "  ✗ Python 3.12+ required. Install from https://python.org"
    exit 1
fi
$PYTHON -m venv "$SCRIPT_DIR/.venv"
source "$SCRIPT_DIR/.venv/bin/activate"
pip install --upgrade pip -q 2>/dev/null
echo "  ✓ venv created"

# ── 2. Dependencies ──
echo "2/5 Installing dependencies..."
pip install httpx pydantic mcp pytest pytest-asyncio -q 2>/dev/null
echo "  ✓ dependencies installed"

# ── 3. Qdrant ──
echo "3/5 Checking Qdrant..."
if curl -s http://127.0.0.1:6333/healthz 2>/dev/null | grep -q "passed"; then
    echo "  ✓ Qdrant already running"
else
    QDRANT_BIN="$SCRIPT_DIR/bin/qdrant"
    if [ -f "$QDRANT_BIN" ]; then
        mkdir -p "$SCRIPT_DIR/storage"
        nohup "$QDRANT_BIN" --config-path "$SCRIPT_DIR/bin/config.yaml" >/dev/null 2>&1 &
        sleep 2
        echo "  ✓ Qdrant started"
    else
        echo "  ⚠ Qdrant binary not found. Install from https://qdrant.tech/documentation/quickstart/"
        echo "    Place binary at: $QDRANT_BIN"
    fi
fi

# ── 4. Embedding model ──
echo "4/5 Checking embedding model..."
if curl -s http://127.0.0.1:8081/health 2>/dev/null | grep -q "ok"; then
    echo "  ✓ Embedding server already running"
else
    mkdir -p "$SCRIPT_DIR/models"
    MODEL="$SCRIPT_DIR/models/bge-m3-Q4_K_M.gguf"
    if [ ! -f "$MODEL" ]; then
        echo "  ⬇  Downloading BGE-M3 model (~417MB)..."
        curl -L -o "$MODEL" "https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf" 2>/dev/null
    fi
    LLAMA_BIN="$SCRIPT_DIR/engine/bin/llama-server"
    if [ -f "$LLAMA_BIN" ]; then
        nohup "$LLAMA_BIN" -m "$MODEL" --port 8081 --host 127.0.0.1 --embedding --pooling mean -ngl 99 --log-disable >/dev/null 2>&1 &
        sleep 3
        echo "  ✓ Embedding server started"
    else
        echo "  ⚠ llama-server not found. Install from https://github.com/ggerganov/llama.cpp"
        echo "    Place binary at: $LLAMA_BIN"
    fi
fi

# ── 5. Config ──
echo "5/5 Generating configuration..."
mkdir -p "$SCRIPT_DIR/config"
cat > "$SCRIPT_DIR/config/.env" << ENVEOF
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
MEMORY_SERVER_DIR=$SCRIPT_DIR
ENVEOF
chmod 600 "$SCRIPT_DIR/config/.env"
echo "  ✓ config/.env created"

# ── Done ──
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║   ✅ Installation complete                         ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "Add to your MCP client config (~/.pi/mcp.json or Claude Desktop):"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "MCP-agent-memory": {'
echo "      \"command\": \"$SCRIPT_DIR/.venv/bin/python3\","
echo "      \"args\": [\"-u\", \"$SCRIPT_DIR/src/unified/server/main.py\"],"
echo "      \"env\": {"
echo "        \"PYTHONPATH\": \"$SCRIPT_DIR/src\","
echo "        \"MEMORY_SERVER_DIR\": \"$SCRIPT_DIR\""
echo '      }'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "Then restart your MCP client."
