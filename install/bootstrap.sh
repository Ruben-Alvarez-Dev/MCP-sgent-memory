#!/bin/bash
# bootstrap.sh — Infrastructure bootstrap for MCP-agent-memory
#
# Sets up the shared infrastructure that ALL apps need:
#   - Python virtual environment (with pyproject.toml deps)
#
# M9 (E2E audit 2026-09-07): the embedding server phase (llama.cpp + BGE-M3)
# is GONE — the engine is FTS5-only; no model binaries are needed.
#
# Usage:
#   bash install/bootstrap.sh [INSTALL_DIR]
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

# ── Step 1/3: Pre-flight ──────────────────────────────────────────
echo -e "${BOLD}[1/3] Pre-flight checks${NC}"
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

# ── Step 2/3: Virtual environment ────────────────────────────────
echo -e "${BOLD}[2/3] Virtual environment${NC}"
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

# ── Step 3/3: Data directories ────────────────────────────────────
echo -e "${BOLD}[3/3] Data directories${NC}"
echo "────────────────────────────────────────────────────────────"

mkdir -p "$INSTALL_DIR/data/memory"/{L3_decisions,dream,thoughts,heartbeats,reminders}
mkdir -p "$INSTALL_DIR/data/staging_buffer"
mkdir -p "$INSTALL_DIR/data/vault"/{Inbox,Decisiones,Conocimiento,Episodios,Entidades,Notes}
pass "Data structure created"

TOTAL_STEPS=3

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
BOOTSTRAP_VENV=$VENV_DIR
BOOTSTRAP_INSTALL_DIR=$INSTALL_DIR
BOOTSTRAP_ERRORS=$ERRORS
BOOTSTRAP_WARNINGS=$WARNINGS
EOF
pass "Status saved to $STATUS_FILE"
