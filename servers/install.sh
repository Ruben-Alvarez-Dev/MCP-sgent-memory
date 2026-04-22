#!/bin/bash
set -e
INSTALL_DIR="${1:-$HOME/MCP-servers/MCP-agent-memory}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SCRIPTS="$(dirname "$SCRIPT_DIR")/install"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Installer v3                     ║"
echo "║   SOLID · DRY · Clean Architecture                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [ -d "$INSTALL_DIR" ]; then
    echo "  ⚠ $INSTALL_DIR exists. Overwrite? (y/N)"
    read -r c; [[ "$c" =~ ^[Yy]$ ]] || exit 0
fi

echo "Installing to: $INSTALL_DIR"
echo ""

# Phase 1: Directory structure
echo "── Phase 1: Structure ─────────────────────────────────"
mkdir -p "$INSTALL_DIR"/{src,config,vault,models,engine/bin,bin,scripts,data}
mkdir -p "$INSTALL_DIR"/src/{automem,autodream,vk-cache,conversation-store,mem0,engram,sequential-thinking,unified}/server
mkdir -p "$INSTALL_DIR"/src/shared/{llm,retrieval,compliance,vault_manager,models,qdrant,workspace}
mkdir -p "$INSTALL_DIR"/data/memory/{engram,dream,thoughts,heartbeats,reminders}
echo "  ✓ Directories created"

# Phase 2: Python environment
echo ""
echo "── Phase 2: Python venv ────────────────────────────────"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3.10 || echo "python3")
"$PY" -m venv "$INSTALL_DIR/.venv"
echo "  ✓ venv created ($("$PY" --version 2>&1))"

# Phase 3: Dependencies (modular)
echo ""
echo "── Phase 3: Dependencies ──────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/deps.sh" ]; then
    bash "$INSTALL_SCRIPTS/deps.sh" "$INSTALL_DIR"
else
    # Fallback: direct install with retry
    for attempt in 1 2 3; do
        if "$INSTALL_DIR/.venv/bin/pip" install --quiet mcp pydantic httpx pyyaml 2>/dev/null; then
            echo "  ✓ Dependencies installed"
            break
        fi
        [ "$attempt" -eq 3 ] && echo "  ⚠ Dependencies failed — install manually"
    done
fi

# Phase 4: Server code
echo ""
echo "── Phase 4: Server code ───────────────────────────────"
for s in automem autodream vk-cache conversation-store mem0 engram sequential-thinking; do
    [ -f "$SCRIPT_DIR/$s/server/main.py" ] && cp "$SCRIPT_DIR/$s/server/main.py" "$INSTALL_DIR/src/$s/server/" && echo "  ✓ $s"
done
[ -d "$SCRIPT_DIR/unified" ] && cp -R "$SCRIPT_DIR/unified/" "$INSTALL_DIR/src/unified/" && echo "  ✓ unified"
for pkg in llm retrieval compliance vault_manager models qdrant workspace; do
    [ -d "$SCRIPT_DIR/shared/$pkg" ] && cp -R "$SCRIPT_DIR/shared/$pkg" "$INSTALL_DIR/src/shared/" 2>/dev/null
done
for f in __init__.py embedding.py env_loader.py observe.py sanitize.py diff_sandbox.py health.py result_models.py config.py qdrant_client.py; do
    [ -f "$SCRIPT_DIR/shared/$f" ] && cp "$SCRIPT_DIR/shared/$f" "$INSTALL_DIR/src/shared/"
done
echo "  ✓ Shared modules copied"

# Phase 5: Configuration (modular)
echo ""
echo "── Phase 5: Configuration ─────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/config.sh" ]; then
    bash "$INSTALL_SCRIPTS/config.sh" "$INSTALL_DIR"
else
    # Inline fallback
    cat > "$INSTALL_DIR/config/.env" << EOF
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
EMBEDDING_DIM=1024
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
VAULT_PATH=$INSTALL_DIR/vault
ENGRAM_PATH=$INSTALL_DIR/data/memory/engram
MEMORY_SERVER_DIR=$INSTALL_DIR
EOF
    cat > "$INSTALL_DIR/config/mcp.json" << EOF
{"mcpServers":{"MCP-agent-memory":{"command":"$INSTALL_DIR/.venv/bin/python3","args":["-u","$INSTALL_DIR/src/unified/server/main.py"],"env":{"PYTHONPATH":"$INSTALL_DIR/src","MEMORY_SERVER_DIR":"$INSTALL_DIR","QDRANT_URL":"http://127.0.0.1:6333"}}}}
EOF
    echo "  ✓ config/.env"
    echo "  ✓ config/mcp.json"
fi

# Phase 6: Services (modular)
echo ""
echo "── Phase 6: Services ──────────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/services.sh" ]; then
    bash "$INSTALL_SCRIPTS/services.sh" "$INSTALL_DIR" 6333 start
else
    echo "  ⚠ services.sh not found"
fi

# Phase 7: Verification (modular)
echo ""
echo "── Phase 7: Verification ──────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/verify.sh" ]; then
    bash "$INSTALL_SCRIPTS/verify.sh" "$INSTALL_DIR"
else
    echo "  ⚠ verify.sh not found — run manually"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ✓ Installation Complete                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location: $INSTALL_DIR"
echo "  Config:   $INSTALL_DIR/config/mcp.json"
echo "  To test:  cp $INSTALL_DIR/config/mcp.json ~/.pi/mcp.json"
echo ""
