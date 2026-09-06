#!/bin/bash
# services.sh — llama-server management
#
# Note: $2 is intentionally ignored (legacy second positional arg, kept for
# backwards compatibility with bootstrap.sh).
set -euo pipefail
SCRIPT_DIR_SVC="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR_SVC="$(dirname "$SCRIPT_DIR_SVC")"
INSTALL_DIR="${1:?Usage: services.sh <install_dir> [legacy_port] [start|stop|status] [llama_port]}"
ACTION="${3:-start}"
LLAMA_PORT="${4:-8081}"

start_llama_server() {
    local MODEL=$(find "$INSTALL_DIR/models" -name "bge-m3*.gguf" | head -1)
    if [ -z "$MODEL" ]; then
        MODEL=$(find "$INSTALL_DIR/models" -name "*.gguf" | head -1)
    fi
    if [ -z "$MODEL" ]; then
        echo "  ⚠ No .gguf model found in $INSTALL_DIR/models/"
        return 1
    fi
    local LLAMA_BIN=$(command -v llama-server 2>/dev/null || echo "$INSTALL_DIR/engine/bin/llama-server")
    if [ ! -x "$LLAMA_BIN" ]; then
        echo "  ⚠ llama-server binary not found"
        return 1
    fi
    nohup "$LLAMA_BIN" -m "$MODEL" --embedding --pooling mean -ngl 99 \
        --host 127.0.0.1 --port "$LLAMA_PORT" \
        > /tmp/llama-server.log 2>&1 &
    echo "  ✓ llama-server starting (port $LLAMA_PORT, model: $(basename "$MODEL"))"
}

stop_llama_server() {
    pkill -f "llama-server.*$LLAMA_PORT" 2>/dev/null && echo "  ✓ llama-server stopped" || echo "  ⚠ llama-server not running"
}

status_llama_server() {
    if curl -s "http://127.0.0.1:$LLAMA_PORT/health" >/dev/null 2>&1; then
        echo "  ✓ llama-server healthy (port $LLAMA_PORT)"
    else
        echo "  ✗ llama-server not responding"
    fi
}

case "$ACTION" in
    start)
        start_llama_server; echo "  ⏳ Waiting for llama-server to load model..."; sleep 15
        ;;
    stop)
        stop_llama_server
        ;;
    status)
        status_llama_server
        ;;
    *)
        echo "Usage: services.sh <install_dir> [legacy_port] [start|stop|status] [llama_port]"
        ;;
esac
