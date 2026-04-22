#!/bin/bash
# services.sh — Qdrant and launchd service management
set -euo pipefail
INSTALL_DIR="${1:?Usage: services.sh <install_dir>}"
QDRANT_PORT="${2:-6333}"

start_qdrant() {
    if [ -f "$INSTALL_DIR/bin/qdrant" ]; then
        "$INSTALL_DIR/bin/qdrant" &
        echo "  ✓ Qdrant starting (port $QDRANT_PORT)"
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
    for col in automem conversations mem0_memories; do
        curl -s -X PUT "http://127.0.0.1:$QDRANT_PORT/collections/$col" \
            -H "Content-Type: application/json" \
            -d '{"vectors":{"size":1024,"distance":"Cosine"},"sparse_vectors":{"text":{"index":{"type":"bm25"}}}}' \
            >/dev/null 2>&1 && echo "  ✓ Collection $col"
    done
}

case "${3:-start}" in
    start) start_qdrant; sleep 2; create_collections ;;
    stop) stop_qdrant ;;
    status) status_qdrant ;;
    *) echo "Usage: services.sh <dir> <port> [start|stop|status]" ;;
esac
