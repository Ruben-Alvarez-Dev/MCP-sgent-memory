#!/bin/bash
# Start embedding server as persistent daemon.
# Uses llama-server with bge-m3 model — 72x faster than subprocess mode.
#
# Usage:
#   ./start-embedding-server.sh          # start on default port 8080
#   LLAMA_SERVER_PORT=9090 ./start-embedding-server.sh  # custom port
#
# The server runs in the background and answers HTTP POST /embedding requests.
# Health check: curl http://127.0.0.1:$PORT/health
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE_DIR="$BASE_DIR/engine"
MODEL_DIR="$BASE_DIR/models"
PORT="${LLAMA_SERVER_PORT:-8080}"
HOST="${LLAMA_SERVER_HOST:-127.0.0.1}"
LOG_FILE="${LLAMA_SERVER_LOG:-$BASE_DIR/embedding-server.log}"
PID_FILE="$BASE_DIR/embedding-server.pid"

# Model selection: prefer bge-m3 (1024 dims, best quality)
MODEL=""
for candidate in \
    "$MODEL_DIR/bge-m3-Q4_K_M.gguf" \
    "$MODEL_DIR/bge-m3"*".gguf" \
    "$MODEL_DIR/"*bge*m3*.gguf \
    "$MODEL_DIR/"*.gguf; do
    if [ -f "$candidate" ]; then
        MODEL="$candidate"
        break
    fi
done

if [ -z "$MODEL" ]; then
    echo "ERROR: No .gguf model found in $MODEL_DIR" >&2
    exit 1
fi

# Check if already running
if curl -sf "http://$HOST:$PORT/health" > /dev/null 2>&1; then
    echo "✅ Embedding server already running on $HOST:$PORT"
    if [ -f "$PID_FILE" ]; then
        echo "   PID: $(cat "$PID_FILE")"
    fi
    exit 0
fi

# Find llama-server binary
SERVER_BIN=""
for path in \
    "$ENGINE_DIR/bin/llama-server" \
    "$(which llama-server 2>/dev/null)"; do
    if [ -x "$path" ]; then
        SERVER_BIN="$path"
        break
    fi
done

if [ -z "$SERVER_BIN" ]; then
    echo "ERROR: llama-server binary not found" >&2
    echo "  Searched: $ENGINE_DIR/bin/llama-server, PATH" >&2
    exit 1
fi

# Kill stale process if PID file exists
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping stale embedding server (PID $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

echo "🚀 Starting embedding server..."
echo "   Binary: $SERVER_BIN"
echo "   Model:  $MODEL"
echo "   Port:   $PORT"
echo "   Log:    $LOG_FILE"

# Set library path for dynamic linking
LIB_DIR="$ENGINE_DIR/lib"
export DYLD_LIBRARY_PATH="$LIB_DIR${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
export LD_LIBRARY_PATH="$LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

nohup "$SERVER_BIN" \
    -m "$MODEL" \
    --embedding \
    --port "$PORT" \
    --host "$HOST" \
    -c 512 \
    -t 4 \
    --mlock \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Wait for ready (max 30 seconds)
echo -n "   Waiting for server..."
for i in $(seq 1 60); do
    if curl -sf "http://$HOST:$PORT/health" > /dev/null 2>&1; then
        echo ""
        echo "✅ Embedding server ready (PID $SERVER_PID)"
        echo "   Latency target: ~15ms per embedding (vs ~1,087ms subprocess)"
        exit 0
    fi
    # Check if process died
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        echo "ERROR: Embedding server process died!" >&2
        echo "  Check log: $LOG_FILE" >&2
        rm -f "$PID_FILE"
        exit 1
    fi
    sleep 0.5
done

echo ""
echo "ERROR: Embedding server failed to start within 30 seconds" >&2
echo "  Check log: $LOG_FILE" >&2
rm -f "$PID_FILE"
exit 1
