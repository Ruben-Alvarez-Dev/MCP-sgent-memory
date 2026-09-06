#!/bin/bash
# bootstrap.sh — Infrastructure bootstrap for MCP-agent-memory
#
# Sets up the shared infrastructure that ALL apps need:
#   - Python virtual environment (with pyproject.toml deps)
#   - Embedding server (BGE-M3 via llama.cpp)
#
# Usage:
#   bash install/bootstrap.sh [INSTALL_DIR]
#   MODEL_PRECISION=Q8 bash install/bootstrap.sh ~/MCP-servers/MCP-agent-memory
#
# Idempotent: safe to run multiple times.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
INSTALL_DIR="${1:-$SCRIPT_DIR/..}"
INSTALL_DIR="$(cd "$INSTALL_DIR" 2>/dev/null && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
import_name() { case "$1" in python-dotenv) echo dotenv;; pyyaml) echo yaml;; *) echo "${1//-/_}";; esac; }
ERRORS=0; WARNINGS=0

# ── Resolve Python ───────────────────────────────────────────────
resolve_python() {
    # Prefer homebrew python to avoid pyenv venv symlink issues
    if command -v /opt/homebrew/opt/python@3.12/bin/python3.12 &>/dev/null; then
        echo "/opt/homebrew/opt/python@3.12/bin/python3.12"
        return
    fi
    # Fall back to pyenv or system
    for candidate in "${PYTHON:-}" python3.14 python3.13 python3.12 python3; do
        if command -v "$candidate" &>/dev/null; then
            realpath "$(command -v "$candidate")" 2>/dev/null || echo "$candidate"
            return
        fi
    done
    echo ""
}

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   MCP-agent-memory — Infrastructure Bootstrap              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1/4: Pre-flight ──────────────────────────────────────────
echo -e "${BOLD}[1/4] Pre-flight checks${NC}"
echo "────────────────────────────────────────────────────────────"

PYTHON_BIN=$(resolve_python)
if [ -z "$PYTHON_BIN" ]; then
    fail "Python 3.12+ not found. Install from python.org or homebrew"
    exit 1
fi
PYVER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || PYVER="0.0")
PYMAJOR=${PYVER%%.*}; PYMINOR=${PYVER##*.}
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 12 ]; }; then
    fail "Python 3.12+ required, found $PYVER"
    exit 1
fi
pass "Python $PYVER ($PYTHON_BIN)"

if [ ! -d "$INSTALL_DIR/src" ]; then
    fail "Source directory not found at $INSTALL_DIR/src"
    exit 1
fi
pass "Source at $INSTALL_DIR"
echo ""

# ── Step 2/4: Virtual environment ────────────────────────────────
echo -e "${BOLD}[2/4] Virtual environment${NC}"
echo "────────────────────────────────────────────────────────────"

VENV_DIR="$INSTALL_DIR/.venv"

if [ -d "$VENV_DIR" ]; then
    # Check if existing venv uses the right Python and has deps
    if [ -f "$VENV_DIR/lib/python3.12/site-packages/mcp/server/fastmcp.py" ] || \
       [ -f "$VENV_DIR/lib/python3.13/site-packages/mcp/server/fastmcp.py" ] || \
       [ -f "$VENV_DIR/lib/python3.14/site-packages/mcp/server/fastmcp.py" ]; then
        # Quick sanity check — can we import the package?
        if "$VENV_DIR/bin/python3" -c "
import sys; sys.path.insert(0, '$INSTALL_DIR/src')
from shared.config import Config; from mcp.server.fastmcp import FastMCP
" 2>/dev/null; then
            pass "venv exists and is functional"
        else
            warn "venv exists but broken — recreating"
            rm -rf "$VENV_DIR"
        fi
    else
        warn "venv exists but missing dependencies — recreating"
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    info "Creating venv..."
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR" --python "$PYTHON_BIN" 2>&1 | tail -1
    elif command -v /opt/homebrew/opt/python@3.12/bin/python3.12 &>/dev/null; then
        /opt/homebrew/opt/python@3.12/bin/python3.12 -m venv "$VENV_DIR"
    else
        $PYTHON_BIN -m venv "$VENV_DIR"
    fi
    pass "venv created"
fi

# Ensure pip is available
if ! "$VENV_DIR/bin/pip" -V &>/dev/null; then
    "$VENV_DIR/bin/python3" -m ensurepip --upgrade 2>/dev/null | tail -1 || true
fi

# Install setuptools if needed (required for pyproject.toml)
"$VENV_DIR/bin/python3" -c "import setuptools" 2>/dev/null || {
    info "Installing setuptools..."
    "$VENV_DIR/bin/pip" install setuptools --quiet 2>/dev/null || \
    "$VENV_DIR/bin/pip" install /opt/homebrew/Cellar/python@3.12/3.12.13/Frameworks/Python.framework/Versions/3.12/lib/python3.12/test/wheeldata/setuptools-79.0.1-py3-none-any.whl --quiet 2>/dev/null || \
    warn "Could not install setuptools — pip install may fail"
}

# Install project with all dependencies via pyproject.toml
if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    PIP="$VENV_DIR/bin/pip"
    if command -v uv &>/dev/null; then
        info "Installing via uv (with cache)..."
        ~/.local/bin/uv pip install -e "$INSTALL_DIR[dev]" --python "$VENV_DIR/bin/python3" 2>&1 | tail -5
    else
        info "Installing via pip..."
        "$PIP" install -e "$INSTALL_DIR[dev]" 2>&1 | tail -5
    fi
else
    warn "No pyproject.toml found — installing deps manually"
    DEPS=("pydantic>=2.0" "httpx>=0.27" "mcp>=1.27" "pydantic-settings>=2.0" "python-dotenv>=1.0")
    for dep in "${DEPS[@]}"; do
        "$VENV_DIR/bin/pip" install "$dep" --quiet 2>/dev/null && pass "$dep" || fail "$dep"
    done
fi

# Verify core imports
"$VENV_DIR/bin/python3" -c "
import sys; sys.path.insert(0, '$INSTALL_DIR/src')
from shared.config import Config
from mcp.server.fastmcp import FastMCP
" 2>/dev/null && pass "Core imports OK" || fail "Core imports failed"
echo ""

# ── Step 3/4: Embedding server ────────────────────────────────────
echo -e "${BOLD}[3/4] Embedding server (BGE-M3)${NC}"
echo "────────────────────────────────────────────────────────────"

EMB_OK=false
EMB_PORT="${EMB_PORT:-8081}"   # allow override when default port is occupied
PRECISION=${MODEL_PRECISION:-Q4_K_M}

if curl -s --max-time 3 http://127.0.0.1:$EMB_PORT/health 2>/dev/null | grep -q "ok"; then
    pass "Embedding server running on :$EMB_PORT"
    EMB_OK=true
else
    mkdir -p "$INSTALL_DIR/models"
    case "$PRECISION" in
        Q4|q4|Q4_K_M) MODEL="$INSTALL_DIR/models/bge-m3-Q4_K_M.gguf" ;;
        Q8|q8|Q8_0)    MODEL="$INSTALL_DIR/models/bge-m3-q8_0.gguf" ;;
        *)              MODEL="$INSTALL_DIR/models/bge-m3-Q4_K_M.gguf" ;;
    esac
    LLAMA_BIN="$INSTALL_DIR/engine/bin/llama-server"
    if [ ! -f "$MODEL" ]; then
        case "$PRECISION" in
            Q4|q4|Q4_K_M) MODEL_URL="https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf" ;;
            Q8|q8|Q8_0)    MODEL_URL="https://huggingface.co/ggml-org/bge-m3-Q8_0-GGUF/resolve/main/bge-m3-q8_0.gguf" ;;
            *)              MODEL_URL="https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf" ;;
        esac
        info "Downloading BGE-M3 model ($PRECISION)..."
        if curl -L --progress-bar -o "$MODEL" "$MODEL_URL" 2>/dev/null; then
            pass "Model downloaded ($(du -h "$MODEL" | awk '{print $1}'))"
        else
            fail "Model download failed (check internet or use MODEL_PRECISION=Q8 for local install)"
        fi
    else
        pass "Model exists ($PRECISION, $(du -h "$MODEL" | awk '{print $1}'))"
    fi
    if [ -f "$LLAMA_BIN" ]; then
        info "Starting embedding server on :$EMB_PORT..."
        nohup "$LLAMA_BIN" -m "$MODEL" --port $EMB_PORT --host 127.0.0.1 --embedding --pooling mean -ngl 99 --log-disable >> "$INSTALL_DIR/embedding.log" 2>&1 &
        sleep 3
        if curl -s --max-time 5 http://127.0.0.1:$EMB_PORT/health 2>/dev/null | grep -q "ok"; then
            pass "Embedding server started (PID $(pgrep -f llama-server | head -1))"
            EMB_OK=true
        else
            fail "llama-server failed to start (check $INSTALL_DIR/embedding.log)"
        fi
    elif command -v cmake &>/dev/null; then
        warn "llama-server binary not found — compiling llama.cpp (2-5 min)..."
        LLAMA_SRC="$INSTALL_DIR/engine/llama.cpp"
        mkdir -p "$INSTALL_DIR/engine/bin"
        if [ ! -d "$LLAMA_SRC" ]; then
            git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_SRC" -q
        fi
        cmake -B "$LLAMA_SRC/build" -S "$LLAMA_SRC" -DLLAMA_METAL=ON -DCMAKE_BUILD_TYPE=Release -DGGML_METAL_USE_BF16=OFF 2>>"$INSTALL_DIR/build.log" && \
        cmake --build "$LLAMA_SRC/build" --config Release -j$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4) --target llama-server 2>>"$INSTALL_DIR/build.log"
        if [ -f "$LLAMA_SRC/build/bin/llama-server" ]; then
            cp "$LLAMA_SRC/build/bin/llama-server" "$LLAMA_BIN"
            chmod +x "$LLAMA_BIN"
            pass "llama-server compiled ($(du -h "$LLAMA_BIN" | awk '{print $1}'))"
            nohup "$LLAMA_BIN" -m "$MODEL" --port $EMB_PORT --host 127.0.0.1 --embedding --pooling mean -ngl 99 --log-disable >> "$INSTALL_DIR/embedding.log" 2>&1 &
            sleep 10
            if curl -s --max-time 5 http://127.0.0.1:$EMB_PORT/health 2>/dev/null | grep -q "ok"; then
                pass "Embedding server started (PID $(pgrep -f llama-server | head -1))"
                EMB_OK=true
            else
                fail "llama-server compiled but failed to start"
            fi
        else
            fail "cmake not found. Install cmake or provide pre-compiled llama-server."
        fi
    else
        fail "llama-server binary not found and cmake unavailable"
    fi
fi
echo ""

# ── Step 4/4: Data directories ────────────────────────────────────
echo -e "${BOLD}[4/4] Data directories${NC}"
echo "────────────────────────────────────────────────────────────"

mkdir -p "$INSTALL_DIR/data/memory"/{L3_decisions,dream,thoughts,heartbeats,reminders}
mkdir -p "$INSTALL_DIR/data/staging_buffer"
mkdir -p "$INSTALL_DIR/data/vault"/{Inbox,Decisiones,Conocimiento,Episodios,Entidades,Notes}
pass "Data structure created"

TOTAL_STEPS=4

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ✅ Bootstrap complete — all $TOTAL_STEPS steps passed${NC}"
    echo -e "${GREEN}${BOLD}  Infrastructure ready for app installation${NC}"
elif [ $ERRORS -lt $TOTAL_STEPS ]; then
    echo -e "${YELLOW}${BOLD}  ⚠ Bootstrap complete with $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo -e "${YELLOW}${BOLD}  App installation may still work — check errors above${NC}"
else
    echo -e "${RED}${BOLD}  ✗ Bootstrap failed — $ERRORS/$TOTAL_STEPS errors${NC}"
    exit 1
fi
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

# Save infrastructure status for app-install.sh to consume
STATUS_FILE="$INSTALL_DIR/.bootstrap-status"
cat > "$STATUS_FILE" << EOF
BOOTSTRAP_EMB=${EMB_OK:-false}
BOOTSTRAP_VENV=$VENV_DIR
BOOTSTRAP_INSTALL_DIR=$INSTALL_DIR
BOOTSTRAP_ERRORS=$ERRORS
BOOTSTRAP_WARNINGS=$WARNINGS
EOF
pass "Status saved to $STATUS_FILE"
