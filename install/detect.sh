#!/bin/bash
# detect.sh - Installation mode detection
set -euo pipefail

INSTALL_DIR="${1:?Usage: detect.sh <install_dir>}"
shift
FORCE_INSTALL=false
REPAIR_MODE=false

for arg in "$@"; do
    case "$arg" in
        --force)   FORCE_INSTALL=true ;;
        --repair)  REPAIR_MODE=true ;;
    esac
done

_dir_bytes() {
    du -sk "$1" 2>/dev/null | cut -f1
}

detect_install_mode() {
    if [ "$REPAIR_MODE" = true ]; then
        echo "repair"
        return 0
    fi
    if [ ! -d "$INSTALL_DIR" ]; then
        echo "install"
        return 0
    fi
    if [ ! -f "$INSTALL_DIR/config/.env" ] && [ ! -f "$INSTALL_DIR/etc/.env" ]; then
        echo "install"
        return 0
    fi
    if [ "$FORCE_INSTALL" = true ]; then
        echo "install"
        return 0
    fi
    echo "update"
    return 0
}

detect_metadata() {
    HAS_DATA=false
    HAS_VAULT=false
    HAS_MODELS=false
    PREV_VERSION="unknown"

    if [ -d "$INSTALL_DIR/data" ]; then
        DATA_SIZE=$(_dir_bytes "$INSTALL_DIR/data")
        if [ "$DATA_SIZE" -gt 1 ]; then
            HAS_DATA=true
        fi
    fi
    if [ -d "$INSTALL_DIR/vault" ]; then
        VAULT_SIZE=$(_dir_bytes "$INSTALL_DIR/vault")
        if [ "$VAULT_SIZE" -gt 1 ]; then
            HAS_VAULT=true
        fi
    fi
    if [ -d "$INSTALL_DIR/models" ]; then
        MODEL_COUNT=$(find "$INSTALL_DIR/models" -name "*.gguf" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$MODEL_COUNT" -gt 0 ]; then
            HAS_MODELS=true
        fi
    fi
    if [ -f "$INSTALL_DIR/install/manifest.json" ]; then
        PREV_VERSION=$(python3 -c "import json; print(json.load(open('$INSTALL_DIR/install/manifest.json')).get('version', 'unknown'))" 2>/dev/null || echo "unknown")
    fi

    export DETECT_HAS_DATA="$HAS_DATA"
    export DETECT_HAS_VAULT="$HAS_VAULT"
    export DETECT_HAS_MODELS="$HAS_MODELS"
    export DETECT_PREV_VERSION="$PREV_VERSION"
}

MODE=$(detect_install_mode)
detect_metadata
echo "MODE=$MODE"
echo "HAS_DATA=$DETECT_HAS_DATA"
echo "HAS_VAULT=$DETECT_HAS_VAULT"
echo "HAS_MODELS=$DETECT_HAS_MODELS"
echo "PREV_VERSION=$DETECT_PREV_VERSION"
