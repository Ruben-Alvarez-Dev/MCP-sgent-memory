#!/bin/bash
# MCP-agent-memory — Installer
# Run from inside the cloned repo: bash install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${1:-$SCRIPT_DIR}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
ERRORS=0; WARNINGS=0

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   MCP-agent-memory — Installer                           ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Pre-flight ──────────────────────────────────────────────────
echo -e "${BOLD}[0/8] Pre-flight checks${NC}"
echo "────────────────────────────────────────────────────────────"

PYTHON="${PYTHON:-python3.12}"
if ! command -v "$PYTHON" &>/dev/null; then PYTHON="python3"; fi
if ! command -v "$PYTHON" &>/dev/null; then fail "Python not found. Install 3.12+ from python.org"; exit 1; fi
PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=${PYVER%%.*}; PYMINOR=${PYVER##*.}
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 12 ]; }; then
    fail "Python 3.12+ required, found $PYVER"; exit 1
fi
pass "Python $PYVER"

if ! command -v git &>/dev/null; then fail "git not found"; exit 1; fi
pass "git $(git --version | awk '{print $3}')"

if [ ! -f "$SCRIPT_DIR/src/unified/server/main.py" ]; then
    fail "Not inside MCP-agent-memory repo. Run: git clone ... && cd MCP-agent-memory && bash install.sh"
    exit 1
fi
pass "Repo detected at $SCRIPT_DIR"
echo ""

# ── Step 1: Virtual environment ─────────────────────────────────
echo -e "${BOLD}[1/8] Python virtual environment${NC}"
echo "────────────────────────────────────────────────────────────"

if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    VENV_VER=$("$SCRIPT_DIR/.venv/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    if [ "$VENV_VER" = "$PYVER" ]; then
        pass "venv exists (Python $VENV_VER)"
    else
        warn "venv Python $VENV_VER ≠ system $PYVER — recreating"
        rm -rf "$SCRIPT_DIR/.venv"
        $PYTHON -m venv "$SCRIPT_DIR/.venv"
        pass "venv recreated (Python $PYVER)"
    fi
else
    $PYTHON -m venv "$SCRIPT_DIR/.venv"
    pass "venv created (Python $PYVER)"
fi

source "$SCRIPT_DIR/.venv/bin/activate"

# Use uv if available (faster + more reliable), fallback to pip
PIP="pip"
if command -v uv &>/dev/null; then
    PIP="uv pip"
fi
$PIP install --upgrade pip -q 2>/dev/null || true
pass "pip upgraded"
echo ""

# ── Step 2: Dependencies ────────────────────────────────────────
echo -e "${BOLD}[2/8] Python dependencies${NC}"
echo "────────────────────────────────────────────────────────────"

DEPS=("pydantic>=2.0" "httpx>=0.27" "mcp>=1.27")
DEVS=("pytest>=8.0" "pytest-asyncio>=0.23")

for dep in "${DEPS[@]}"; do
    $PIP install "$dep" -q 2>/dev/null
    pkg=$(echo "$dep" | sed 's/[>=<].*//')
    if python3 -c "import $pkg" 2>/dev/null; then pass "$dep"; else fail "$dep"; fi
done
for dep in "${DEVS[@]}"; do
    $PIP install "$dep" -q 2>/dev/null
    pkg=$(echo "$dep" | sed 's/[>=<].*//')
    if python3 -c "import ${pkg//-/_}" 2>/dev/null; then pass "$dep (dev)"; else fail "$dep"; fi
done
echo ""

# ── Step 3: Qdrant ──────────────────────────────────────────────
echo -e "${BOLD}[3/8] Qdrant vector database${NC}"
echo "────────────────────────────────────────────────────────────"

QDRANT_OK=false
if curl -s --max-time 3 http://127.0.0.1:6333/healthz 2>/dev/null | grep -q "passed"; then
    pass "Qdrant running on :6333"
    QDRANT_OK=true
elif [ -f "$SCRIPT_DIR/bin/qdrant" ]; then
    mkdir -p "$SCRIPT_DIR/bin/storage" "$SCRIPT_DIR/bin/snapshots"
    nohup "$SCRIPT_DIR/bin/qdrant" --config-path "$SCRIPT_DIR/bin/config.yaml" >> "$SCRIPT_DIR/qdrant.log" 2>&1 &
    sleep 2
    if curl -s --max-time 3 http://127.0.0.1:6333/healthz 2>/dev/null | grep -q "passed"; then
        pass "Qdrant started (PID $(pgrep -f 'bin/qdrant' | head -1))"
        QDRANT_OK=true
    else
        fail "Qdrant binary exists but failed to start (check qdrant.log)"
    fi
else
    warn "Qdrant not found. Install:"
    info "macOS:  brew install qdrant"
    info "Linux:  curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz | tar xz"
    info "Place binary at: $SCRIPT_DIR/bin/qdrant"
    WARNINGS=$((WARNINGS+1))
fi
echo ""

# ── Step 4: Embedding server ────────────────────────────────────
echo -e "${BOLD}[4/8] Embedding server (BGE-M3 via llama.cpp)${NC}"
echo "────────────────────────────────────────────────────────────"

EMB_OK=false
if curl -s --max-time 3 http://127.0.0.1:8081/health 2>/dev/null | grep -q "ok"; then
    pass "Embedding server running on :8081"
    EMB_OK=true
else
    mkdir -p "$SCRIPT_DIR/models"
    MODEL="$SCRIPT_DIR/models/bge-m3-Q4_K_M.gguf"
    LLAMA_BIN="$SCRIPT_DIR/engine/bin/llama-server"
    if [ ! -f "$MODEL" ]; then
        info "Downloading BGE-M3 model (~417MB)..."
        if curl -L --progress-bar -o "$MODEL" "https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf" 2>/dev/null; then
            pass "Model downloaded ($(du -h "$MODEL" | awk '{print $1}'))"
        else
            fail "Model download failed"
        fi
    else
        pass "Model exists ($(du -h "$MODEL" | awk '{print $1}'))"
    fi
    if [ -f "$LLAMA_BIN" ]; then
        nohup "$LLAMA_BIN" -m "$MODEL" --port 8081 --host 127.0.0.1 --embedding --pooling mean -ngl 99 --log-disable >> "$SCRIPT_DIR/embedding.log" 2>&1 &
        sleep 3
        if curl -s --max-time 5 http://127.0.0.1:8081/health 2>/dev/null | grep -q "ok"; then
            pass "Embedding server started (PID $(pgrep -f llama-server | head -1))"
            EMB_OK=true
        else
            fail "llama-server failed to start (check embedding.log)"
        fi
    else
        warn "llama-server not found. Install llama.cpp:"
        info "macOS:  brew install llama.cpp"
        info "Linux:  git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make -j"
        info "Place binary at: $LLAMA_BIN"
        WARNINGS=$((WARNINGS+1))
    fi
fi
echo ""

# ── Step 5: Ollama ──────────────────────────────────────────────
echo -e "${BOLD}[5/8] Ollama (LLM backend)${NC}"
echo "────────────────────────────────────────────────────────────"

if curl -s --max-time 3 http://localhost:11434/api/tags 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('models') else 1)" 2>/dev/null; then
    MODEL_COUNT=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))")
    pass "Ollama running ($MODEL_COUNT models)"
elif command -v ollama &>/dev/null; then
    warn "Ollama installed but not running. Start with: ollama serve"
    WARNINGS=$((WARNINGS+1))
else
    warn "Ollama not found. Install from https://ollama.ai"
    info "Then run: ollama pull qwen2.5:7b"
    WARNINGS=$((WARNINGS+1))
fi
echo ""

# ── Step 6: Configuration ───────────────────────────────────────
echo -e "${BOLD}[6/8] Configuration${NC}"
echo "────────────────────────────────────────────────────────────"

mkdir -p "$SCRIPT_DIR/config"
cat > "$SCRIPT_DIR/config/.env" << EOF
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
MEMORY_SERVER_DIR=$SCRIPT_DIR
VAULT_PATH=$SCRIPT_DIR/data/vault
ENGRAM_PATH=$SCRIPT_DIR/data/memory/engram
DREAM_PATH=$SCRIPT_DIR/data/memory/dream
THOUGHTS_PATH=$SCRIPT_DIR/data/memory/thoughts
HEARTBEATS_PATH=$SCRIPT_DIR/data/memory/heartbeats
REMINDERS_PATH=$SCRIPT_DIR/data/memory/reminders
STAGING_BUFFER=$SCRIPT_DIR/data/staging_buffer
AUTOMEM_JSONL=$SCRIPT_DIR/data/raw_events.jsonl
EOF
chmod 600 "$SCRIPT_DIR/config/.env"
pass "config/.env created"

mkdir -p "$SCRIPT_DIR/data/memory"/{engram,dream,thoughts,heartbeats,reminders}
mkdir -p "$SCRIPT_DIR/data"/{staging_buffer,vault}/{Inbox,Decisiones,Conocimiento,Episodios,Entidades,Notes}
pass "Directory structure created"
echo ""

# ── Step 7: MCP client config ───────────────────────────────────
echo -e "${BOLD}[7/8] MCP client configuration${NC}"
echo "────────────────────────────────────────────────────────────"

MCP_JSON='{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "'"$SCRIPT_DIR"'/.venv/bin/python3",
      "args": ["-u", "'"$SCRIPT_DIR"'/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "'"$SCRIPT_DIR"'/src",
        "MEMORY_SERVER_DIR": "'"$SCRIPT_DIR"'",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_BACKEND": "llama_server",
        "LLAMA_SERVER_URL": "http://127.0.0.1:8081",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}'

# Save standalone config
echo "$MCP_JSON" | python3 -m json.tool > "$SCRIPT_DIR/config/mcp.json" 2>/dev/null || echo "$MCP_JSON" > "$SCRIPT_DIR/config/mcp.json"
pass "config/mcp.json generated"

# Detect and configure MCP clients
CONFIGURED=0
for CLIENT_CONFIG in "$HOME/.pi/mcp.json" "$HOME/.config/claude/claude_desktop_config.json"; do
    CLIENT_DIR=$(dirname "$CLIENT_CONFIG")
    if [ -d "$CLIENT_DIR" ] || [ -f "$CLIENT_CONFIG" ]; then
        mkdir -p "$CLIENT_DIR"
        if [ -f "$CLIENT_CONFIG" ]; then
            # Merge into existing config
            EXISTING=$(cat "$CLIENT_CONFIG")
            MERGED=$(echo "$EXISTING" | python3 -c "
import sys, json
try:
    existing = json.load(sys.stdin)
except:
    existing = {}
new_servers = $MCP_JSON
existing.setdefault('mcpServers', {}).update(new_servers['mcpServers'])
json.dump(existing, sys.stdout, indent=2)
" 2>/dev/null)
            if [ -n "$MERGED" ]; then
                echo "$MERGED" > "$CLIENT_CONFIG"
                pass "Updated $(basename "$CLIENT_CONFIG")"
                CONFIGURED=$((CONFIGURED+1))
            fi
        else
            echo "$MCP_JSON" | python3 -m json.tool > "$CLIENT_CONFIG" 2>/dev/null
            pass "Created $(basename "$CLIENT_CONFIG")"
            CONFIGURED=$((CONFIGURED+1))
        fi
    fi
done
if [ "$CONFIGURED" -eq 0 ]; then
    info "No MCP client detected. Copy config/mcp.json to your client's config location."
fi
echo ""

# ── Step 8: Verification ────────────────────────────────────────
echo -e "${BOLD}[8/8] Verification${NC}"
echo "────────────────────────────────────────────────────────────"

VERIFY_OK=0; VERIFY_TOTAL=0

# Test 1: Python imports
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if "$SCRIPT_DIR/.venv/bin/python3" -c "
import sys; sys.path.insert(0,'$SCRIPT_DIR/src')
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.sanitize import sanitize_text
print('imports_ok')
" 2>/dev/null | grep -q "imports_ok"; then
    pass "Python imports"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Python imports"
fi

# Test 2: Config validation
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if "$SCRIPT_DIR/.venv/bin/python3" -c "
import sys; sys.path.insert(0,'$SCRIPT_DIR/src')
from shared.config import Config
c = Config.from_env()
errs = c.validate()
print('config_ok' if not errs else f'config_errors: {errs}')
" 2>/dev/null | grep -q "config_ok"; then
    pass "Config validation"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Config validation"
fi

# Test 3: Qdrant connectivity
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if [ "$QDRANT_OK" = true ]; then
    if "$SCRIPT_DIR/.venv/bin/python3" -c "
import sys, asyncio; sys.path.insert(0,'$SCRIPT_DIR/src')
from shared.config import Config; from shared.qdrant_client import QdrantClient
async def test():
    c = Config.from_env()
    q = QdrantClient(c.qdrant_url, c.qdrant_collection, c.embedding_dim)
    return await q.health()
print('qdrant_ok' if asyncio.run(test()) else 'qdrant_fail')
" 2>/dev/null | grep -q "qdrant_ok"; then
        pass "Qdrant connectivity"
        VERIFY_OK=$((VERIFY_OK+1))
    else
        fail "Qdrant connectivity"
    fi
else
    warn "Qdrant not available — skipped"
fi

# Test 4: Embedding
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if [ "$EMB_OK" = true ]; then
    # Load env vars from config/.env for the test
    set -a; [ -f "$SCRIPT_DIR/config/.env" ] && source "$SCRIPT_DIR/config/.env"; set +a
    if "$SCRIPT_DIR/.venv/bin/python3" -c "
import sys; sys.path.insert(0,'$SCRIPT_DIR/src')
from shared.embedding import get_embedding
v = get_embedding('test')
print(f'embed_ok dim={len(v)}' if len(v)==1024 else f'embed_fail dim={len(v)}')
" 2>/dev/null | grep -q "embed_ok"; then
        pass "Embedding generation (1024 dims)"
        VERIFY_OK=$((VERIFY_OK+1))
    else
        fail "Embedding generation"
    fi
else
    warn "Embedding server not available — skipped"
fi

# Test 5: Unit tests
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
TEST_RESULT=$("$SCRIPT_DIR/.venv/bin/python3" -m pytest "$SCRIPT_DIR/tests/" -q --tb=no 2>/dev/null | tail -1)
if echo "$TEST_RESULT" | grep -q "passed"; then
    pass "Unit tests ($TEST_RESULT)"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Unit tests ($TEST_RESULT)"
fi
echo ""

# ── Summary ─────────────────────────────────────────────────────
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ✅ All checks passed ($VERIFY_OK/$VERIFY_TOTAL verified)${NC}"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}${BOLD}  ⚠  Installation complete with $WARNINGS warning(s) ($VERIFY_OK/$VERIFY_TOTAL verified)${NC}"
else
    echo -e "${RED}${BOLD}  ✗ Installation complete with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
fi
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart your MCP client (Pi, Claude Desktop, etc.)"
echo "  2. The MCP-agent-memory tools should appear automatically"
echo "  3. Test with: memory_store(content='installation test', tags='setup')"
echo ""
echo "Services that need to be running:"
echo "  • Qdrant:      http://127.0.0.1:6333"
echo "  • Embedding:   http://127.0.0.1:8081"
echo "  • Ollama:      http://localhost:11434"
echo ""
