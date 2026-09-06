#!/bin/bash
# MCP-agent-memory — Installer
#
# Two-phase install:
#   Phase 1: bootstrap.sh  → venv + embedding server (BGE-M3 via llama.cpp)
#   Phase 2: app-install.sh → config, MCP client setup, verification
#
# Usage (one-liner, no clone needed):
#   curl -fsSL https://raw.githubusercontent.com/Ruben-Alvarez-Dev/MCP-agent-memory/main/install.sh | bash
#   curl -fsSL ... | bash -s -- ~/my-custom-path
#
# Or from inside the cloned repo:
#   bash install.sh
#   bash install.sh ~/my-custom-path
#
# Use Q8 embedding precision instead of default Q4:
#   MODEL_PRECISION=Q8 bash install.sh
#
# Run only app config (skip infrastructure):
#   bash install.sh --app-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
INSTALL_DIR="${1:-$SCRIPT_DIR}"

# ── Flags ──
APP_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --app-only) APP_ONLY=true ;;
        *) INSTALL_DIR="$arg" ;;
    esac
done

# ── Auto-bootstrap: download source via tarball if not inside repo ──
if [ ! -f "$INSTALL_DIR/src/unified/server/main.py" ]; then
    REPO_URL="https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory"
    echo ""
    echo "⬇  Downloading MCP-agent-memory source..."

    TMPDIR=$(mktemp -d -t mcp-mem.XXXXXX)
    cleanup() { rm -rf "$TMPDIR"; }
    trap cleanup EXIT

    if ! curl -fsSL "${REPO_URL}/archive/refs/heads/main.tar.gz" -o "$TMPDIR/src.tar.gz"; then
        echo "  ✗ Download failed. Check your internet connection."
        exit 1
    fi

    mkdir -p "$TMPDIR/repo"
    tar -xzf "$TMPDIR/src.tar.gz" -C "$TMPDIR/repo" --strip-components=1
    rm -rf "$TMPDIR/repo/.git"

    # Copy only what's needed (skip heavy engine sources, docs, bench)
    mkdir -p "$INSTALL_DIR"
    rm -rf "$INSTALL_DIR/engine/llama.cpp" 2>/dev/null || true
    for item in src install config deps install.sh run-daemon.sh pyproject.toml bin tests README.md .python-version .gitignore; do
        [ -e "$TMPDIR/repo/$item" ] && cp -a "$TMPDIR/repo/$item" "$INSTALL_DIR/"
    done
    echo "  ✓ Source installed at $INSTALL_DIR ($(du -sh "$INSTALL_DIR" | awk '{print $1}'))"

    # Re-exec from the installed location
    exec bash "$INSTALL_DIR/install.sh" "$INSTALL_DIR" ${APP_ONLY:+--app-only}
fi

# Resolve to absolute path
INSTALL_DIR="$(cd "$INSTALL_DIR" 2>/dev/null && pwd)"

# ── Phase 1: Infrastructure bootstrap ──
if [ "$APP_ONLY" = false ]; then
    if [ -f "$INSTALL_DIR/install/bootstrap.sh" ]; then
        bash "$INSTALL_DIR/install/bootstrap.sh" "$INSTALL_DIR"
        # Source the status file that bootstrap created
        [ -f "$INSTALL_DIR/.bootstrap-status" ] && source "$INSTALL_DIR/.bootstrap-status"
    else
        echo "✗ install/bootstrap.sh not found at $INSTALL_DIR"
        exit 1
    fi
else
    echo "→ Skipping bootstrap (--app-only)"
    [ -f "$INSTALL_DIR/.bootstrap-status" ] && source "$INSTALL_DIR/.bootstrap-status"
fi

# ── Phase 2: App configuration & verification ──
if [ -f "$INSTALL_DIR/install/app-install.sh" ]; then
    bash "$INSTALL_DIR/install/app-install.sh" "$INSTALL_DIR"
else
    echo "✗ install/app-install.sh not found at $INSTALL_DIR"
    exit 1
fi
