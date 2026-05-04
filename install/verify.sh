#!/bin/bash
# verify.sh — Full post-installation verification
set -euo pipefail
INSTALL_DIR="${1:?Usage: verify.sh <install_dir>}"
PYTHON="$INSTALL_DIR/.venv/bin/python3"
QDRANT_PORT="${2:-6333}"
LLAMA_PORT="${3:-8081}"
PASS=0; FAIL=0

check() { if [ -e "$1" ]; then echo "  ✓ $2"; PASS=$((PASS+1)); else echo "  ✗ $2"; FAIL=$((FAIL+1)); fi }
check_cmd() { if command -v "$1" &>/dev/null; then echo "  ✓ $2"; PASS=$((PASS+1)); else echo "  ✗ $2"; FAIL=$((FAIL+1)); fi }
check_url() { if curl -sf "$1" >/dev/null 2>&1; then echo "  ✓ $2"; PASS=$((PASS+1)); else echo "  ✗ $2"; FAIL=$((FAIL+1)); fi }

echo "── Verification ─────────────────────────────────────"

# 1. File structure
echo "  [Files]"
for mod in L0_capture L0_to_L4_consolidation L5_routing L2_conversations L3_facts L3_decisions Lx_reasoning; do
    check "$INSTALL_DIR/src/$mod/server/main.py" "src/$mod/server/main.py"
done
check "$INSTALL_DIR/src/unified/server/main.py" "unified server"
check "$INSTALL_DIR/config/.env" "config/.env"
check "$INSTALL_DIR/config/mcp.json" "config/mcp.json"

# 2. Binaries (compiled from source in engine/bin)
echo "  [Binaries]"
check "$INSTALL_DIR/engine/bin/llama-server" "engine/bin/llama-server"

# 3. Embedding model
echo "  [Embedding Model]"
MODEL_COUNT=$(find "$INSTALL_DIR/models" -name "*.gguf" 2>/dev/null | wc -l | tr -d ' ')
if [ "$MODEL_COUNT" -gt 0 ]; then
    echo "  ✓ Model files found ($MODEL_COUNT)"; PASS=$((PASS+1))
    MODEL=$(find "$INSTALL_DIR/models" -name "*.gguf" | head -1)
    SIZE=$(du -h "$MODEL" 2>/dev/null | cut -f1)
    echo "    → $(basename "$MODEL") ($SIZE)"
else
    echo "  ✗ No .gguf models in $INSTALL_DIR/models/"; FAIL=$((FAIL+1))
fi

# 4. Services
echo "  [Services]"
check_url "http://127.0.0.1:$QDRANT_PORT/healthz" "Qdrant (port $QDRANT_PORT)"
check_url "http://127.0.0.1:$LLAMA_PORT/health" "llama-server (port $LLAMA_PORT)"

# 5. Qdrant collections
echo "  [Qdrant Collections]"
for col in L0_L4_memory L2_conversations L3_facts; do
    if curl -sf "http://127.0.0.1:$QDRANT_PORT/collections/$col" >/dev/null 2>&1; then
        echo "  ✓ Collection $col"; PASS=$((PASS+1))
    else
        echo "  ✗ Collection $col missing"; FAIL=$((FAIL+1))
    fi
done

# 4. Embeddings working (uses venv python, not system python3)
echo "  [Embeddings]"
EMB_RESULT=$(curl -sf -X POST "http://127.0.0.1:$LLAMA_PORT/v1/embeddings" \
    -H "Content-Type: application/json" \
    -d '{"input":"test","model":"bge-m3"}' 2>/dev/null) && EMB_OK=true || EMB_OK=false

if [ "$EMB_OK" = "true" ]; then
    EMB_DIMS=$(echo "$EMB_RESULT" | "$PYTHON" -c "
import sys, json
data = json.load(sys.stdin)
if isinstance(data, list):
    emb = data[0].get('embedding', [])
elif isinstance(data, dict):
    emb = data.get('data', [{}])[0].get('embedding', [])
else:
    emb = []
print(len(emb))
" 2>/dev/null) || EMB_DIMS=0
    if [ "$EMB_DIMS" -ge 384 ]; then
        echo "  ✓ Embeddings working ($EMB_DIMS dimensions)"; PASS=$((PASS+1))
    else
        echo "  ✗ Embeddings wrong dimensionality ($EMB_DIMS)"; FAIL=$((FAIL+1))
    fi
else
    echo "  ✗ Embeddings not working"; FAIL=$((FAIL+1))
fi

# 7. Python imports
echo "  [Python]"
if PYTHONPATH="$INSTALL_DIR/src" "$PYTHON" -c "
import sys; sys.path.insert(0, '$INSTALL_DIR/src')
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.qdrant_client import QdrantClient
from shared.result_models import MemorizeResult
import importlib.util
spec = importlib.util.spec_from_file_location('unified', '$INSTALL_DIR/src/unified/server/main.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(f'  ✓ Unified: {len(m.mcp._tool_manager._tools)} tools, {len(m._loaded)} modules')
" 2>/dev/null; then
    PASS=$((PASS+1))
else
    echo "  ✗ Unified server failed to load"; FAIL=$((FAIL+1))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then echo "  ✅ All checks passed ($PASS)"; else echo "  ⚠ $FAIL checks failed ($PASS passed)"; fi
exit $FAIL
