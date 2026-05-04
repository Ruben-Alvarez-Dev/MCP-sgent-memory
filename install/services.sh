#!/bin/bash
# services.sh — Qdrant + llama-server management
set -euo pipefail
SCRIPT_DIR_SVC="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR_SVC="$(dirname "$SCRIPT_DIR_SVC")"
INSTALL_DIR="${1:?Usage: services.sh <install_dir> [qdrant_port] [start|stop|status] [llama_port]}"
QDRANT_PORT="${2:-6333}"
ACTION="${3:-start}"
LLAMA_PORT="${4:-8081}"

start_qdrant() {
    if [ -f "$INSTALL_DIR/bin/qdrant" ]; then
        "$INSTALL_DIR/bin/qdrant" &
        echo "  ✓ Qdrant starting (port $QDRANT_PORT)"
    elif [ -f "$REPO_DIR_SVC/servers/shared/qdrant/qdrant" ]; then
        mkdir -p "$INSTALL_DIR/bin"
        cp "$REPO_DIR_SVC/servers/shared/qdrant/qdrant" "$INSTALL_DIR/bin/"
        cp "$REPO_DIR_SVC/servers/shared/qdrant/config.yaml" "$INSTALL_DIR/bin/" 2>/dev/null || true
        chmod +x "$INSTALL_DIR/bin/qdrant"
        "$INSTALL_DIR/bin/qdrant" &
        echo "  ✓ Qdrant starting (from bundled binary, port $QDRANT_PORT)"
    elif command -v qdrant &>/dev/null; then
        qdrant &
        echo "  ✓ Qdrant starting (system)"
    else
        echo "  ⚠ Qdrant not found"
    fi
}

stop_qdrant() {
    pkill -f "qdrant" 2>/dev/null && echo "  ✓ Qdrant stopped" || echo "  ⚠ Qdrant not running"
}

status_qdrant() {
    if curl -s "http://127.0.0.1:$QDRANT_PORT/healthz" >/dev/null 2>&1; then
        echo "  ✓ Qdrant healthy (port $QDRANT_PORT)"
    else
        echo "  ✗ Qdrant not responding"
    fi
}

create_collections() {
    # L0_L4_memory: dense + sparse (BM25 hybrid search)
    curl -s -X PUT "http://127.0.0.1:$QDRANT_PORT/collections/L0_L4_memory" \
        -H "Content-Type: application/json" \
        -d '{"vectors":{"size":1024,"distance":"Cosine"},"sparse_vectors":{"text":{"index":{"type":"bm25"}}}}' \
        >/dev/null 2>&1 && echo "  ✓ Collection L0_L4_memory (dense+sparse)"
    # L2_conversations: dense only
    curl -s -X PUT "http://127.0.0.1:$QDRANT_PORT/collections/L2_conversations" \
        -H "Content-Type: application/json" \
        -d '{"vectors":{"size":1024,"distance":"Cosine"}}' \
        >/dev/null 2>&1 && echo "  ✓ Collection L2_conversations (dense)"
    # L3_facts: dense only
    curl -s -X PUT "http://127.0.0.1:$QDRANT_PORT/collections/L3_facts" \
        -H "Content-Type: application/json" \
        -d '{"vectors":{"size":1024,"distance":"Cosine"}}' \
        >/dev/null 2>&1 && echo "  ✓ Collection L3_facts (dense)"
}

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
        start_qdrant; sleep 2; create_collections
        start_llama_server; echo "  ⏳ Waiting for llama-server to load model..."; sleep 15
        ;;
    stop)
        stop_qdrant; stop_llama_server
        ;;
    status)
        status_qdrant; status_llama_server
        ;;
    *)
        echo "Usage: services.sh <dir> <qdrant_port> [start|stop|status] [llama_port]"
        ;;
esac
