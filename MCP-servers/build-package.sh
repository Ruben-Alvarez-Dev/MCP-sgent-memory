#!/bin/bash
set -e

# ═══════════════════════════════════════════════════════════════════
# build-package.sh — Assembles a distributable installer package
#
# Scans multiple sources for engine/models/qdrant binaries,
# copies everything into a staging directory that install.sh can
# consume as a self-contained package.
#
# Usage:
#   ./build-package.sh                     # build to ./dist/
#   INSTALL_DIR=/tmp/mcp-pkg ./build-package.sh
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STAGE="${INSTALL_DIR:-$SCRIPT_DIR/dist/MCP-memory-server}"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Package Builder                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Clean staging
rm -rf "$STAGE"
mkdir -p "$STAGE"

# ── 1. Server code (flat layout for install.sh compatibility) ──────

echo "📦 Copying server code..."
SERVERS="automem autodream vk-cache conversation-store mem0 engram sequential-thinking  "

for server in $SERVERS; do
    mkdir -p "$STAGE/$server/server"
    if [ -f "$SCRIPT_DIR/$server/server/main.py" ]; then
        cp "$SCRIPT_DIR/$server/server/main.py" "$STAGE/$server/server/"
        echo "  ✓ $server"
    else
        echo "  ⚠ $server not found"
    fi
done

# ── 2. Shared modules ──────────────────────────────────────────────

echo "📦 Copying shared modules..."
mkdir -p "$STAGE/shared"
cp "$SCRIPT_DIR/shared/embedding.py" "$STAGE/shared/" 2>/dev/null || true
cp "$SCRIPT_DIR/shared/__init__.py" "$STAGE/shared/" 2>/dev/null || true
cp "$SCRIPT_DIR/shared/env_loader.py" "$STAGE/shared/" 2>/dev/null || true
cp "$SCRIPT_DIR/shared/observe.py" "$STAGE/shared/" 2>/dev/null || true

for pkg in llm retrieval compliance vault_manager models qdrant; do
    if [ -d "$SCRIPT_DIR/shared/$pkg" ]; then
        # Clean __pycache__ before copy
        find "$SCRIPT_DIR/shared/$pkg" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        cp -R "$SCRIPT_DIR/shared/$pkg" "$STAGE/shared/"
        echo "  ✓ shared/$pkg"
    fi
done

# ── 3. Engine (llama.cpp) — resolve from multiple sources ──────────

echo ""
echo "🔍 Resolving engine binaries..."

ENGINE_FOUND=false

# Source 1: Existing production install
PROD_ENGINE="$HOME/MCP-servers/MCP-memory-server/bin/engine"
if [ -d "$PROD_ENGINE/bin" ] && [ -f "$PROD_ENGINE/bin/llama-embedding" ]; then
    mkdir -p "$STAGE/engine/bin" "$STAGE/engine/lib"
    cp "$PROD_ENGINE/bin/llama-embedding" "$STAGE/engine/bin/"
    cp "$PROD_ENGINE/bin/llama-server" "$STAGE/engine/bin/" 2>/dev/null || true
    cp "$PROD_ENGINE/lib/"*.dylib "$STAGE/engine/lib/" 2>/dev/null || true
    cp "$PROD_ENGINE/lib/"*.so "$STAGE/engine/lib/" 2>/dev/null || true
    echo "  ✓ Engine from production install"
    ENGINE_FOUND=true
fi

# Source 2: Dev engine/ directory
if [ "$ENGINE_FOUND" = "false" ] && [ -d "$SCRIPT_DIR/engine/bin" ]; then
    mkdir -p "$STAGE/engine/bin" "$STAGE/engine/lib"
    cp -R "$SCRIPT_DIR/engine/bin/"* "$STAGE/engine/bin/"
    cp -R "$SCRIPT_DIR/engine/lib/"* "$STAGE/engine/lib/" 2>/dev/null || true
    echo "  ✓ Engine from dev directory"
    ENGINE_FOUND=true
fi

# Source 3: Homebrew llama.cpp
if [ "$ENGINE_FOUND" = "false" ] && command -v llama-embedding &>/dev/null; then
    mkdir -p "$STAGE/engine/bin" "$STAGE/engine/lib"
    BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
    cp "$(command -v llama-embedding)" "$STAGE/engine/bin/"
    cp "$(command -v llama-server)" "$STAGE/engine/bin/" 2>/dev/null || true
    # Copy shared libs
    if [ -d "$BREW_PREFIX/Cellar/llama.cpp" ]; then
        LIB_DIR=$(find "$BREW_PREFIX/Cellar/llama.cpp" -name "libllama*.dylib" -print -quit 2>/dev/null | xargs dirname)
        if [ -n "$LIB_DIR" ]; then
            cp "$LIB_DIR/"*.dylib "$STAGE/engine/lib/" 2>/dev/null || true
        fi
    fi
    echo "  ✓ Engine from Homebrew ($(command -v llama-embedding))"
    ENGINE_FOUND=true
fi

if [ "$ENGINE_FOUND" = "false" ]; then
    echo "  ⚠ No engine found. Install llama.cpp or provide engine/ directory."
fi

# ── 4. Models — resolve from multiple sources ──────────────────────

echo ""
echo "🔍 Resolving embedding models..."

MODEL_FOUND=false

# Source 1: Dev models/
if ls "$SCRIPT_DIR/models/"*.gguf &>/dev/null; then
    mkdir -p "$STAGE/models"
    cp "$SCRIPT_DIR/models/"*.gguf "$STAGE/models/"
    echo "  ✓ Models from dev directory"
    MODEL_FOUND=true
fi

# Source 2: Production install
if [ "$MODEL_FOUND" = "false" ] && [ -d "$HOME/MCP-servers/MCP-memory-server/bin/models" ]; then
    mkdir -p "$STAGE/models"
    cp "$HOME/MCP-servers/MCP-memory-server/bin/models/"*.gguf "$STAGE/models/"
    echo "  ✓ Models from production install"
    MODEL_FOUND=true
fi

if [ "$MODEL_FOUND" = "false" ]; then
    echo "  ⚠ No models found. Add .gguf files to models/ or install to production first."
fi

# ── 5. Qdrant binary ──────────────────────────────────────────────

echo ""
echo "🔍 Resolving Qdrant binary..."

QDRANT_FOUND=false

# Source 1: Bundled in shared/qdrant/
if [ -f "$SCRIPT_DIR/shared/qdrant/qdrant" ]; then
    mkdir -p "$STAGE/shared/qdrant"
    cp "$SCRIPT_DIR/shared/qdrant/qdrant" "$STAGE/shared/qdrant/"
    cp "$SCRIPT_DIR/shared/qdrant/config.yaml" "$STAGE/shared/qdrant/" 2>/dev/null || true
    echo "  ✓ Qdrant from bundled"
    QDRANT_FOUND=true
fi

# Source 2: Production
if [ "$QDRANT_FOUND" = "false" ] && [ -f "$HOME/MCP-servers/MCP-memory-server/bin/qdrant" ]; then
    mkdir -p "$STAGE/shared/qdrant"
    cp "$HOME/MCP-servers/MCP-memory-server/bin/qdrant" "$STAGE/shared/qdrant/"
    cp "$SCRIPT_DIR/shared/qdrant/config.yaml" "$STAGE/shared/qdrant/" 2>/dev/null || true
    echo "  ✓ Qdrant from production"
    QDRANT_FOUND=true
fi

# ── 6. Config templates ────────────────────────────────────────────

echo ""
echo "📦 Copying config templates..."
mkdir -p "$STAGE/config"
if [ -f "$SCRIPT_DIR/config/.env.example" ]; then
    cp "$SCRIPT_DIR/config/.env.example" "$STAGE/config/"
    echo "  ✓ config/.env.example"
fi

# ── 7. Vault templates ────────────────────────────────────────────

echo "📦 Creating vault templates..."
mkdir -p "$STAGE/vault/Templates"
cat > "$STAGE/vault/Templates/Decision.md" << 'TEMPLATE'
---
type: decision
date: {{date}}
scope: {{scope}}
tags: [{{tags}}]
---

# {{title}}

## Contexto
{{context}}

## Decisión
{{decision}}

## Consecuencias
{{consequences}}
TEMPLATE

cat > "$STAGE/vault/Templates/Entidad.md" << 'TEMPLATE'
---
type: entity
date: {{date}}
tags: [{{tags}}]
---

# {{title}}

## Descripción
{{description}}

## Relaciones
{{relations}}
TEMPLATE

cat > "$STAGE/vault/Templates/Patron.md" << 'TEMPLATE'
---
type: pattern
date: {{date}}
tags: [{{tags}}]
---

# {{title}}

## Problema
{{problem}}

## Solución
{{solution}}

## Ejemplo
{{example}}
TEMPLATE

echo "  ✓ vault/Templates (3 templates)"

# ── 8. Installer ───────────────────────────────────────────────────

cp "$SCRIPT_DIR/install.sh" "$STAGE/"
chmod +x "$STAGE/install.sh"
echo "  ✓ install.sh"

# ── 9. Re-sign binaries on macOS ───────────────────────────────────

if [ "$(uname -s)" = "Darwin" ]; then
    echo ""
    echo "🔐 Signing binaries..."
    for bin in "$STAGE/engine/bin/"* "$STAGE/shared/qdrant/qdrant"; do
        [ -f "$bin" ] && codesign --force --sign - "$bin" 2>/dev/null && echo "  ✓ $(basename $bin)"
    done
    for lib in "$STAGE/engine/lib/"*.dylib; do
        [ -f "$lib" ] && codesign --force --sign - "$lib" 2>/dev/null || true
    done
fi

# ── Summary ────────────────────────────────────────────────────────

TOTAL_SIZE=$(du -sh "$STAGE" 2>/dev/null | awk '{print $1}')
SERVER_COUNT=$(ls -d "$STAGE"/*/server/main.py 2>/dev/null | wc -l | tr -d ' ')
MODEL_COUNT=$(ls "$STAGE/models/"*.gguf 2>/dev/null | wc -l | tr -d ' ')
ENGINE_BIN=$(ls "$STAGE/engine/bin/" 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Package Built!                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location:   $STAGE ($TOTAL_SIZE)"
echo "  Servers:    $SERVER_COUNT"
echo "  Models:     $MODEL_COUNT (.gguf)"
echo "  Engine:     $ENGINE_BIN binaries"
echo ""
echo "  To install:"
echo "    cd $STAGE && ./install.sh"
echo ""
echo "  To create .dmg (macOS):"
echo "    hdiutil create -volname 'MCP Memory Server' -srcfolder '$STAGE' -ov -format UDZO MCP-Memory-Server.dmg"
