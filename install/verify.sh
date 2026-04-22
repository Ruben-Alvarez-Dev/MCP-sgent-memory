#!/bin/bash
# verify.sh — Post-installation verification
set -euo pipefail
INSTALL_DIR="${1:?Usage: verify.sh <install_dir>}"
PYTHON="$INSTALL_DIR/.venv/bin/python3"
PASS=0; FAIL=0

check() { if [ -e "$1" ]; then echo "  ✓ $2"; PASS=$((PASS+1)); else echo "  ✗ $2"; FAIL=$((FAIL+1)); fi }

echo "── Verification ─────────────────────────────────────"
for mod in automem autodream vk-cache conversation-store mem0 engram sequential-thinking; do
    check "$INSTALL_DIR/src/$mod/server/main.py" "src/$mod/server/main.py"
done
check "$INSTALL_DIR/src/unified/server/main.py" "unified server"
check "$INSTALL_DIR/config/.env" "config/.env"
check "$INSTALL_DIR/config/mcp.json" "config/mcp.json"

# Python import test
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
    echo "  ✗ Unified server failed to load"
    FAIL=$((FAIL+1))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then echo "  ✅ All checks passed ($PASS)"; else echo "  ⚠ $FAIL checks failed ($PASS passed)"; fi
return $FAIL 2>/dev/null || exit $FAIL
