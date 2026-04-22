#!/bin/bash
# deps.sh — Dependency management with multi-strategy fallback
# Strategy: venv pip → system pip --target → copy from system
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${1:?Usage: deps.sh <install_dir>}"
VENV="$INSTALL_DIR/.venv"
PYTHON_VENV="$VENV/bin/python3"
MANIFEST="$SCRIPT_DIR/manifest.json"

log() { echo "  $1"; }
fail() { echo "  ✗ $1" >&2; return 1; }

# ── Strategy 1: venv pip direct ──────────────────────────────────
install_via_venv_pip() {
    log "Strategy 1: venv pip install..."
    local pkgs=$(python3 -c "import json; [print(d['name']) for d in json.load(open('$MANIFEST'))['dependencies']]")
    if "$VENV/bin/pip" install --quiet $pkgs 2>/dev/null; then
        log "  ✓ venv pip succeeded"
        return 0
    fi
    log "  ⚠ venv pip failed (network issue)"
    return 1
}

# ── Strategy 2: system pip --target ──────────────────────────────
install_via_system_pip() {
    log "Strategy 2: system pip --target..."
    local tmpdir=$(mktemp -d)
    local pkgs=$(python3 -c "import json; [print(d['name']) for d in json.load(open('$MANIFEST'))['dependencies']]")
    
    # Try with python3 (system)
    if python3 -m pip install --quiet --target "$tmpdir" $pkgs 2>/dev/null; then
        local site=$("$PYTHON_VENV" -c "import site; print(site.getsitepackages()[0])")
        cp -r "$tmpdir"/* "$site/" 2>/dev/null
        rm -rf "$tmpdir"
        log "  ✓ system pip --target succeeded"
        return 0
    fi
    rm -rf "$tmpdir"
    log "  ⚠ system pip --target failed"
    return 1
}

# ── Strategy 3: copy from system python ──────────────────────────
install_via_system_copy() {
    log "Strategy 3: copy from system python..."
    local site=$("$PYTHON_VENV" -c "import site; print(site.getsitepackages()[0])")
    local copied=0
    
    for pkg_info in $(python3 -c "
import json
for d in json.load(open('$MANIFEST'))['dependencies']:
    print(d['import'] + '|' + d['name'])
"); do
        local import_name=$(echo "$pkg_info" | cut -d'|' -f1)
        local pkg_name=$(echo "$pkg_info" | cut -d'|' -f2)
        
        # Find package in system python
        local pkg_path=$(python3 -c "
import $import_name, os
p = $import_name.__file__
print(os.path.dirname(p) if '__init__' in p else p)
" 2>/dev/null || echo "")
        
        if [ -n "$pkg_path" ] && [ -e "$pkg_path" ]; then
            if [ -d "$pkg_path" ]; then
                cp -r "$pkg_path" "$site/" 2>/dev/null && copied=$((copied + 1))
            else
                cp "$pkg_path" "$site/" 2>/dev/null && copied=$((copied + 1))
            fi
        fi
    done
    
    if [ "$copied" -gt 0 ]; then
        log "  ✓ copied $copied packages from system"
        return 0
    fi
    log "  ✗ no packages found in system python"
    return 1
}

# ── Validate installation ────────────────────────────────────────
validate() {
    log "Validating dependencies..."
    local ok=0
    local fail=0
    
    for import_name in $(python3 -c "
import json
for d in json.load(open('$MANIFEST'))['dependencies']:
    print(d['import'])
"); do
        if "$PYTHON_VENV" -c "import $import_name" 2>/dev/null; then
            ok=$((ok + 1))
        else
            local critical=$(python3 -c "
import json
for d in json.load(open('$MANIFEST'))['dependencies']:
    if d['import'] == '$import_name':
        print(d['critical'])
        break
")
            if [ "$critical" = "True" ]; then
                fail=$((fail + 1))
                log "  ✗ $import_name (CRITICAL)"
            else
                log "  ⚠ $import_name (optional)"
            fi
        fi
    done
    
    log "  Result: $ok ok, $fail critical missing"
    return $fail
}

# ── Main ─────────────────────────────────────────────────────────
main() {
    log "── Dependency Installation ─────────────────────────"
    
    install_via_venv_pip && validate && return 0
    install_via_system_pip && validate && return 0
    install_via_system_copy && validate && return 0
    
    log "  ✗ All strategies failed"
    return 1
}

main
