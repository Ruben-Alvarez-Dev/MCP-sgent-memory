#!/bin/bash
# deps.sh — Dependency installation with 3-strategy fallback
# Strategy 1: Bundled wheels (offline, always works)
# Strategy 2: venv pip (online)
# Strategy 3: system pip --target
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="${1:?Usage: deps.sh <install_dir>}"
VENV_PIP="$INSTALL_DIR/.venv/bin/pip"
VENV_PY="$INSTALL_DIR/.venv/bin/python3"
WHEELS_DIR="$REPO_DIR/deps/vendor"

log() { echo "  $1"; }

validate() {
    local ok=0 fail=0
    for import_name in pydantic httpx mcp yaml; do
        if "$VENV_PY" -c "import $import_name" 2>/dev/null; then
            ok=$((ok+1))
        else
            fail=$((fail+1))
            log "  ✗ $import_name"
        fi
    done
    log "  Result: $ok/4 ok"
    return $fail
}

# Strategy 1: Bundled wheels (offline)
install_from_wheels() {
    log "Strategy 1: bundled wheels..."
    if [ -d "$WHEELS_DIR" ] && ls "$WHEELS_DIR"/*.whl >/dev/null 2>&1; then
        if "$VENV_PIP" install --no-index --find-links "$WHEELS_DIR" "$WHEELS_DIR"/*.whl 2>/dev/null; then
            log "  ✓ wheels installed"
            return 0
        fi
    fi
    log "  ⚠ wheels not found or failed"
    return 1
}

# Strategy 2: venv pip (online)
install_from_pip() {
    log "Strategy 2: venv pip..."
    if "$VENV_PIP" install --quiet mcp pydantic httpx pyyaml 2>/dev/null; then
        log "  ✓ pip install succeeded"
        return 0
    fi
    log "  ⚠ pip install failed"
    return 1
}

# Strategy 3: download wheels then install
install_via_download() {
    log "Strategy 3: download wheels..."
    local tmpdir=$(mktemp -d)
    local pyver=$("$VENV_PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local platform=$("$VENV_PY" -c "import platform; print(platform.system().lower())")
    local arch=$("$VENV_PY" -c "import platform; m=platform.machine(); print('x86_64' if m=='x86_64' or m=='AMD64' else 'aarch64')")
    local plat_tag="${platform}_${arch}"
    log "  Downloading for Python $pyver ($plat_tag)..."
    if pip3 download --only-binary=:all: --python-version "$pyver" --platform "$plat_tag" \
        -d "$tmpdir" mcp pydantic httpx pyyaml 2>/dev/null; then
        if "$VENV_PIP" install --no-index --find-links "$tmpdir" "$tmpdir"/*.whl 2>/dev/null; then
            rm -rf "$tmpdir"
            log "  ✓ downloaded and installed"
            return 0
        fi
    fi
    rm -rf "$tmpdir"
    log "  ⚠ download failed"
    return 1
}

main() {
    log "── Dependency Installation ─────────────────────────"
    
    install_from_wheels && validate && return 0
    install_from_pip && validate && return 0
    install_via_download && validate && return 0
    
    log "  ✗ All strategies failed"
    return 1
}

main
