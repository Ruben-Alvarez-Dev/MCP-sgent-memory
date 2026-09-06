#!/bin/bash
# app-install.sh — Application configuration & verification for MCP-agent-memory
#
# Configures the MCP server for a specific app/client:
#   - config/.env (server configuration)
#   - config/mcp.json (MCP client configuration)
#   - Client config auto-merge (opencode, claude, cursor, etc.)
#   - Verification (imports, config, memory.db, embedding, tests)
#
# Requires: bootstrap.sh must have been run first (creates .venv, .bootstrap-status)
#
# Usage:
#   bash install/app-install.sh [INSTALL_DIR]
#   bash install/app-install.sh ~/MCP-servers/MCP-agent-memory
#
# Idempotent: safe to run multiple times.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
INSTALL_DIR="${1:-$SCRIPT_DIR/..}"
INSTALL_DIR="$(cd "$INSTALL_DIR" 2>/dev/null && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; WARNINGS=$((WARNINGS+1)); }
info() { echo -e "  ${CYAN}→${NC} $1"; }
ERRORS=0; WARNINGS=0

echo ""
echo -e "${BOLD}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   MCP-agent-memory — App Install                        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Load bootstrap status ─────────────────────────────────────────
if [ -f "$INSTALL_DIR/.bootstrap-status" ]; then
    source "$INSTALL_DIR/.bootstrap-status"
    pass "Bootstrap status loaded (Emb=$BOOTSTRAP_EMB)"
else
    warn "No .bootstrap-status found — infrastructure may not be set up"
    BOOTSTRAP_EMB=false
    BOOTSTRAP_VENV="$INSTALL_DIR/.venv"
fi

if [ ! -d "$BOOTSTRAP_VENV" ]; then
    fail "Virtual environment not found at $BOOTSTRAP_VENV"
    fail "Run bootstrap.sh first: bash install/bootstrap.sh"
    exit 1
fi

PYTHON="$BOOTSTRAP_VENV/bin/python3"
if [ ! -f "$PYTHON" ]; then
    fail "Python not found at $PYTHON"
    exit 1
fi
pass "Python: $PYTHON"
echo ""

# ── Step 1/4: Configuration ────────────────────────────────────────
echo -e "${BOLD}[1/4] Configuration${NC}"
echo "────────────────────────────────────────────────────────────"

mkdir -p "$INSTALL_DIR/config"
if [ -f "$INSTALL_DIR/config/.env" ]; then
    chmod 600 "$INSTALL_DIR/config/.env" 2>/dev/null || true
    # Validate existing .env has required keys
    MISSING=""
    for key in EMBEDDING_BACKEND LLAMA_SERVER_URL EMBEDDING_DIM; do
        grep -q "^${key}=" "$INSTALL_DIR/config/.env" 2>/dev/null || MISSING="$MISSING $key"
    done
    if [ -n "$MISSING" ]; then
        warn "config/.env missing keys:$MISSING — appending defaults"
        cat >> "$INSTALL_DIR/config/.env" << EOF
# Appended by app-install.sh $(date +%Y-%m-%d)
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
EOF
        pass "config/.env updated with missing keys"
    else
        pass "config/.env preserved (existing, all keys present)"
    fi
else
    cat > "$INSTALL_DIR/config/.env" << EOF
EMBEDDING_BACKEND=llama_server
LLAMA_SERVER_URL=http://127.0.0.1:8081
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
MEMORY_SERVER_DIR=$INSTALL_DIR
VAULT_PATH=$INSTALL_DIR/data/vault
STAGING_BUFFER=$INSTALL_DIR/data/staging_buffer
EOF
    chmod 600 "$INSTALL_DIR/config/.env"
    pass "config/.env created"
fi
echo ""

# ── Step 2/4: MCP client configuration ────────────────────────────
echo -e "${BOLD}[2/4] MCP client configuration${NC}"
echo "────────────────────────────────────────────────────────────"

MCP_JSON='{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "'"$INSTALL_DIR"'/.venv/bin/python3",
      "args": ["-u", "'"$INSTALL_DIR"'/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "'"$INSTALL_DIR"'/src",
        "MEMORY_SERVER_DIR": "'"$INSTALL_DIR"'",
        "EMBEDDING_BACKEND": "llama_server",
        "LLAMA_SERVER_URL": "http://127.0.0.1:8081",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}'

echo "$MCP_JSON" | $PYTHON -m json.tool > "$INSTALL_DIR/config/mcp.json" 2>/dev/null || echo "$MCP_JSON" > "$INSTALL_DIR/config/mcp.json"
pass "config/mcp.json generated"

# Auto-merge into detected client configs
CONFIGURED=0
CLIENT_CONFIGS=(
    "$HOME/.pi/mcp.json"
    "$HOME/.config/claude/claude_desktop_config.json"
    "$HOME/.config/opencode/opencode.json"
    "$HOME/.cursor/mcp.json"
)

for CLIENT_CONFIG in "${CLIENT_CONFIGS[@]}"; do
    CLIENT_DIR=$(dirname "$CLIENT_CONFIG")
    if [ -d "$CLIENT_DIR" ] || [ -f "$CLIENT_CONFIG" ]; then
        mkdir -p "$CLIENT_DIR"
        if [ -f "$CLIENT_CONFIG" ]; then
            # Merge — preserve existing servers, add/update ours
            MERGED=$($PYTHON -c "
import sys, json
try:
    existing = json.load(open('$CLIENT_CONFIG'))
except:
    existing = {}
new_servers = json.loads('''$MCP_JSON''')['mcpServers']
# Handle opencode.json which nests differently
if 'mcpServers' not in existing and 'servers' in existing:
    for name, cfg in new_servers.items():
        existing['servers'][name] = cfg
    json.dump(existing, sys.stdout, indent=2)
else:
    existing.setdefault('mcpServers', {}).update(new_servers)
    json.dump(existing, sys.stdout, indent=2)
" 2>/dev/null)
            if [ -n "$MERGED" ]; then
                echo "$MERGED" > "$CLIENT_CONFIG"
                pass "Updated $(basename "$CLIENT_CONFIG")"
                CONFIGURED=$((CONFIGURED+1))
            fi
        else
            echo "$MCP_JSON" | $PYTHON -m json.tool > "$CLIENT_CONFIG" 2>/dev/null
            pass "Created $(basename "$CLIENT_CONFIG")"
            CONFIGURED=$((CONFIGURED+1))
        fi
    fi
done
if [ "$CONFIGURED" -eq 0 ]; then
    info "No MCP client detected. Copy config/mcp.json to your client's config location."
fi
echo ""

# ── Step 3/4: Verification ────────────────────────────────────────
echo -e "${BOLD}[3/4] Verification${NC}"
echo "────────────────────────────────────────────────────────────"

VERIFY_OK=0; VERIFY_TOTAL=0

# 1. Python imports
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if $PYTHON -c "
import sys; sys.path.insert(0,'$INSTALL_DIR/src')
from shared.config import Config
from shared.sanitize import sanitize_text
print('imports_ok')
" 2>/dev/null | grep -q "imports_ok"; then
    pass "Python imports"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Python imports"
fi

# 2. Config validation
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if $PYTHON -c "
import sys; sys.path.insert(0,'$INSTALL_DIR/src')
from shared.config import Config
c = Config.from_env()
errs = c.validate()
print('config_ok' if not errs else f'config_errors: {errs}')
" 2>/dev/null | grep -q "config_ok"; then
    pass "Config validation"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Config validation"
fi

# 3. Memory DB (memory.db)
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if $PYTHON -c "
import sys, asyncio; sys.path.insert(0,'$INSTALL_DIR/src')
from shared.memory_db import MemoryDB
async def test():
    db = MemoryDB(None, 'L0_L4_memory', 1024)
    await db.ensure_collection()
    return await db.health()
print('memory_db_ok' if asyncio.run(test()) else 'memory_db_fail')
" 2>/dev/null | grep -q "memory_db_ok"; then
    pass "Memory DB (memory.db)"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Memory DB (memory.db)"
fi

# 4. Embedding generation
VERIFY_TOTAL=$((VERIFY_TOTAL+1))
if [ "$BOOTSTRAP_EMB" = true ]; then
    set -a; [ -f "$INSTALL_DIR/config/.env" ] && source "$INSTALL_DIR/config/.env"; set +a
    if $PYTHON -c "
import sys; sys.path.insert(0,'$INSTALL_DIR/src')
from shared.embedding import get_embedding
v = get_embedding('test')
print(f'embed_ok dim={len(v)}' if len(v)==1024 else f'embed_fail dim={len(v)}')
" 2>/dev/null | grep -q "embed_ok"; then
        pass "Embedding generation (1024 dims)"
        VERIFY_OK=$((VERIFY_OK+1))
    else
        fail "Embedding generation"
    fi
else
    warn "Embedding server not available — skipped"
fi
echo ""

# ── Step 4/4: Unit tests ──────────────────────────────────────────
echo -e "${BOLD}[4/4] Unit tests${NC}"
echo "────────────────────────────────────────────────────────────"

VERIFY_TOTAL=$((VERIFY_TOTAL+1))
TEST_RESULT=$($PYTHON -m pytest "$INSTALL_DIR/tests/" -q --tb=no 2>/dev/null | tail -1)
if echo "$TEST_RESULT" | grep -q "passed"; then
    pass "Unit tests ($TEST_RESULT)"
    VERIFY_OK=$((VERIFY_OK+1))
else
    fail "Unit tests ($TEST_RESULT)"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ✅ App install complete ($VERIFY_OK/$VERIFY_TOTAL verified)${NC}"
    echo -e "${GREEN}${BOLD}  MCP-agent-memory ready to use${NC}"
elif [ $ERRORS -lt $VERIFY_TOTAL ]; then
    echo -e "${YELLOW}${BOLD}  ⚠  App install complete with $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo -e "${YELLOW}${BOLD}  ($VERIFY_OK/$VERIFY_TOTAL verified)${NC}"
else
    echo -e "${RED}${BOLD}  ✗ App install failed — $ERRORS errors${NC}"
fi
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Service startup hints ─────────────────────────────────────────
if [ "$BOOTSTRAP_EMB" = false ]; then
    echo -e "${BOLD}Services not running — start manually if needed:${NC}"
    echo ""
    if [ -f "$INSTALL_DIR/engine/bin/llama-server" ]; then
        echo -e "  ${CYAN}Embedding:${NC} $INSTALL_DIR/engine/bin/llama-server -m $INSTALL_DIR/models/bge-m3-Q4_K_M.gguf --port 8081 --host 127.0.0.1 --embedding --pooling mean -ngl 99 --log-disable"
    fi
    echo ""
else
    echo -e "${GREEN}${BOLD}All services running. Restart your MCP client.${NC}"
fi
echo ""
