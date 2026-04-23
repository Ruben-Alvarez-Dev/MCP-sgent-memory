#!/bin/bash
set -e
INSTALL_DIR="${1:-$HOME/MCP-servers/MCP-agent-memory}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SCRIPTS="$(dirname "$SCRIPT_DIR")/install"
LLAMA_PORT="${2:-8081}"

# ── Auto-bootstrap: if run via "curl | bash", download repo automatically ──
if [ ! -f "$SCRIPT_DIR/automem/server/main.py" ]; then
    REPO_URL="https://github.com/Ruben-Alvarez-Dev/MCP-sgent-memory.git"
    BOOTSTRAP_DIR=$(mktemp -d -t mcp-memory.XXXXXX)
    echo "  Downloading MCP-agent-memory..."
    git clone --depth 1 --filter=blob:none --sparse "$REPO_URL" "$BOOTSTRAP_DIR/repo" 2>/dev/null
    cd "$BOOTSTRAP_DIR/repo"
    git sparse-checkout set servers install deps 2>/dev/null
    echo "  ✓ Downloaded to $BOOTSTRAP_DIR/repo"
    echo ""
    # Re-execute from the downloaded repo
    bash "$BOOTSTRAP_DIR/repo/servers/install.sh" "$@" 
    _exit_code=$?
    rm -rf "$BOOTSTRAP_DIR"
    exit $_exit_code
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   MCP Memory Server — Installer v4                     ║"
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

# Phase 5: llama.cpp compilation + Embedding model
echo ""
echo "── Phase 5: Embeddings (llama.cpp + BGE-M3) ──────────"

# Check if already compiled
if [ -x "$INSTALL_DIR/engine/bin/llama-server" ] && [ -x "$INSTALL_DIR/engine/bin/llama-embedding" ]; then
    echo "  ✓ llama.cpp already compiled in engine/bin/"
else
    # Check for cmake
    if ! command -v cmake &>/dev/null; then
        echo "  ✗ cmake not found. Install with: brew install cmake"
        exit 1
    fi

    # Clone llama.cpp
    LLAMA_BUILD_DIR=$(mktemp -d)
    echo "  Cloning llama.cpp..."
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_BUILD_DIR/llama.cpp" || { echo "  ✗ git clone failed"; exit 1; }

    # Detect platform and set build flags
    BUILD_FLAGS=""
    if [ "$(uname)" = "Darwin" ]; then
        # macOS: compile with Metal for GPU acceleration
        BUILD_FLAGS="-DGGML_METAL=ON"
        echo "  Platform: macOS — compiling with Metal support"
    elif [ "$(uname)" = "Linux" ]; then
        # Linux: check for CUDA
        if command -v nvidia-smi &>/dev/null; then
            BUILD_FLAGS="-DGGML_CUDA=ON"
            echo "  Platform: Linux — compiling with CUDA support"
        else
            echo "  Platform: Linux — compiling CPU-only"
        fi
    fi

    # Compile
    echo "  Compiling llama.cpp (this may take a few minutes)..."
    cmake -S "$LLAMA_BUILD_DIR/llama.cpp" -B "$LLAMA_BUILD_DIR/build" \
        -DCMAKE_BUILD_TYPE=Release \
        $BUILD_FLAGS \
        -DLLAMA_BUILD_SERVER=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=OFF \
        2>/dev/null

    NPROC=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
    cmake --build "$LLAMA_BUILD_DIR/build" --config Release -j$NPROC

    # Copy binaries
    for bin in llama-server llama-embedding llama-cli; do
        if [ -f "$LLAMA_BUILD_DIR/build/bin/$bin" ]; then
            cp "$LLAMA_BUILD_DIR/build/bin/$bin" "$INSTALL_DIR/engine/bin/"
        elif [ -f "$LLAMA_BUILD_DIR/build/$bin" ]; then
            cp "$LLAMA_BUILD_DIR/build/$bin" "$INSTALL_DIR/engine/bin/"
        fi
    done

    # Cleanup
    rm -rf "$LLAMA_BUILD_DIR"

    if [ -x "$INSTALL_DIR/engine/bin/llama-server" ]; then
        echo "  ✓ llama.cpp compiled and installed to engine/bin/"
    else
        echo "  ✗ Compilation failed — check build logs"
        exit 1
    fi
fi

# Download BGE-M3 model
MODEL_FILE="$INSTALL_DIR/models/bge-m3-Q4_K_M.gguf"
if [ -f "$MODEL_FILE" ]; then
    echo "  ✓ BGE-M3 model already present ($(du -h "$MODEL_FILE" | cut -f1))"
else
    echo "  Downloading BGE-M3 model (417MB)..."
    if curl -L -o "$MODEL_FILE" "https://huggingface.co/gpustack/bge-m3-GGUF/resolve/main/bge-m3-Q4_K_M.gguf" 2>/dev/null; then
        echo "  ✓ BGE-M3 downloaded ($(du -h "$MODEL_FILE" | cut -f1))"
    else
        echo "  ⚠ Download failed — download manually from:"
        echo "    https://huggingface.co/gpustack/bge-m3-GGUF"
    fi
fi

# Phase 6: Configuration (modular)
echo ""
echo "── Phase 6: Configuration ─────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/config.sh" ]; then
    bash "$INSTALL_SCRIPTS/config.sh" "$INSTALL_DIR" 6333 "$LLAMA_PORT"
else
    # Inline fallback
    cat > "$INSTALL_DIR/config/.env" << EOF
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_BACKEND=llama_server
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
LLAMA_SERVER_URL=http://127.0.0.1:$LLAMA_PORT
LLM_BACKEND=ollama
LLM_MODEL=qwen2.5:7b
VAULT_PATH=$INSTALL_DIR/vault
ENGRAM_PATH=$INSTALL_DIR/data/memory/engram
DREAM_PATH=$INSTALL_DIR/data/memory/dream
THOUGHTS_PATH=$INSTALL_DIR/data/memory/thoughts
HEARTBEATS_PATH=$INSTALL_DIR/data/memory/heartbeats
REMINDERS_PATH=$INSTALL_DIR/data/memory/reminders
STAGING_BUFFER=$INSTALL_DIR/data/staging_buffer
AUTOMEM_JSONL=$INSTALL_DIR/data/raw_events.jsonl
MEMORY_SERVER_DIR=$INSTALL_DIR
EOF
    cat > "$INSTALL_DIR/config/mcp.json" << EOF
{
  "mcpServers": {
    "MCP-agent-memory": {
      "command": "$INSTALL_DIR/.venv/bin/python3",
      "args": ["-u", "$INSTALL_DIR/src/unified/server/main.py"],
      "env": {
        "PYTHONPATH": "$INSTALL_DIR/src",
        "MEMORY_SERVER_DIR": "$INSTALL_DIR",
        "QDRANT_URL": "http://127.0.0.1:6333",
        "EMBEDDING_BACKEND": "llama_server",
        "LLAMA_SERVER_URL": "http://127.0.0.1:$LLAMA_PORT",
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_DIM": "1024"
      }
    }
  }
}
EOF
    echo "  ✓ config/.env"
    echo "  ✓ config/mcp.json"
fi

# Phase 7: Services (modular)
echo ""
echo "── Phase 7: Services ──────────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/services.sh" ]; then
    bash "$INSTALL_SCRIPTS/services.sh" "$INSTALL_DIR" 6333 start "$LLAMA_PORT"
else
    # Inline fallback: start Qdrant + llama-server + create collections
    _qp=6333
    _lp="$LLAMA_PORT"

    # -- Qdrant --
    if curl -sf "http://127.0.0.1:$_qp/healthz" >/dev/null 2>&1; then
        echo "  ✓ Qdrant already running (port $_qp)"
    else
        _qb=""
        if [ -x "$INSTALL_DIR/bin/qdrant" ]; then
            _qb="$INSTALL_DIR/bin/qdrant"
        elif [ -f "$SCRIPT_DIR/shared/qdrant/qdrant" ]; then
            mkdir -p "$INSTALL_DIR/bin"
            cp "$SCRIPT_DIR/shared/qdrant/qdrant" "$INSTALL_DIR/bin/"
            cp "$SCRIPT_DIR/shared/qdrant/config.yaml" "$INSTALL_DIR/bin/" 2>/dev/null || true
            chmod +x "$INSTALL_DIR/bin/qdrant"
            _qb="$INSTALL_DIR/bin/qdrant"
        elif command -v qdrant &>/dev/null; then
            _qb="$(command -v qdrant)"
        fi
        if [ -n "$_qb" ]; then
            nohup "$_qb" --config-path "$INSTALL_DIR/bin/config.yaml" >/tmp/qdrant-mcp.log 2>&1 &
            echo "  ✓ Qdrant starting (port $_qp)"
            for _i in $(seq 1 20); do curl -sf "http://127.0.0.1:$_qp/healthz" >/dev/null 2>&1 && break; sleep 1; done
        else
            echo "  ⚠ Qdrant binary not found — install: brew install qdrant"
        fi
    fi

    # -- Collections --
    for _c in automem conversations mem0_memories; do
        curl -sf -X PUT "http://127.0.0.1:$_qp/collections/$_c"             -H "Content-Type: application/json"             -d '{"vectors":{"size":1024,"distance":"Cosine"},"sparse_vectors":{"text":{"index":{"type":"bm25"}}}}' >/dev/null 2>&1
        echo "  ✓ Collection $_c"
    done

    # -- llama-server --
    if curl -sf "http://127.0.0.1:$_lp/health" >/dev/null 2>&1; then
        echo "  ✓ llama-server already running (port $_lp)"
    else
        _m=$(find "$INSTALL_DIR/models" -name "*.gguf" 2>/dev/null | head -1)
        _lb="$INSTALL_DIR/engine/bin/llama-server"
        if [ -x "$_lb" ] && [ -n "$_m" ]; then
            nohup "$_lb" -m "$_m" --embedding --pooling mean -ngl 99                 --host 127.0.0.1 --port "$_lp" >/tmp/llama-server-mcp.log 2>&1 &
            echo "  ✓ llama-server starting (port $_lp, loading model — up to 120s)"
            for _i in $(seq 1 120); do curl -sf "http://127.0.0.1:$_lp/health" >/dev/null 2>&1 && break; sleep 1; done
            curl -sf "http://127.0.0.1:$_lp/health" >/dev/null 2>&1 && echo "  ✓ llama-server healthy" || echo "  ⚠ llama-server not responding"
        else
            echo "  ⚠ llama-server binary or model not found"
        fi
    fi
fi

# Phase 8: Verification (modular)
echo ""
echo "── Phase 8: Verification ──────────────────────────────"
if [ -f "$INSTALL_SCRIPTS/verify.sh" ]; then
    bash "$INSTALL_SCRIPTS/verify.sh" "$INSTALL_DIR" 6333 "$LLAMA_PORT"
else
    # Inline fallback: comprehensive verification
    _vp="$INSTALL_DIR/.venv/bin/python3"
    _qp=6333; _lp="$LLAMA_PORT"; _ok=0; _ko=0
    _ck() { if [ -e "$1" ]; then echo "  ✓ $2"; _ok=$((_ok+1)); else echo "  ✗ $2"; _ko=$((_ko+1)); fi }
    _cu() { if curl -sf "$1" >/dev/null 2>&1; then echo "  ✓ $2"; _ok=$((_ok+1)); else echo "  ✗ $2"; _ko=$((_ko+1)); fi }

    echo "  [Files]"
    for _m in automem autodream vk-cache conversation-store mem0 engram sequential-thinking; do
        _ck "$INSTALL_DIR/src/$_m/server/main.py" "src/$_m/server/main.py"
    done
    _ck "$INSTALL_DIR/src/unified/server/main.py" "unified server"
    _ck "$INSTALL_DIR/config/.env" "config/.env"
    _ck "$INSTALL_DIR/config/mcp.json" "config/mcp.json"

    echo "  [Binaries]"
    _ck "$INSTALL_DIR/engine/bin/llama-server" "llama-server (compiled with Metal)"
    _ck "$INSTALL_DIR/engine/bin/llama-cli" "llama-cli"

    echo "  [Model]"
    _mc=$(find "$INSTALL_DIR/models" -name "*.gguf" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$_mc" -gt 0 ]; then
        _mm=$(find "$INSTALL_DIR/models" -name "*.gguf" | head -1)
        echo "  ✓ Model: $(basename "$_mm") ($(du -h "$_mm" | cut -f1))"; _ok=$((_ok+1))
    else echo "  ✗ No .gguf models"; _ko=$((_ko+1)); fi

    echo "  [Services]"
    _cu "http://127.0.0.1:$_qp/healthz" "Qdrant (port $_qp)"
    _cu "http://127.0.0.1:$_lp/health" "llama-server (port $_lp)"

    echo "  [Collections]"
    for _c in automem conversations mem0_memories; do
        _cu "http://127.0.0.1:$_qp/collections/$_c" "collection $_c"
    done

    echo "  [Embeddings]"
    _eb=$(curl -sf -X POST "http://127.0.0.1:$_lp/embedding" -H "Content-Type: application/json" -d '{"content":"test"}' 2>/dev/null)
    if [ -n "$_eb" ]; then
        _dm=$(echo "$_eb" | "$_vp" -c "import sys,json; d=json.load(sys.stdin); print(len(d[0]['embedding']) if isinstance(d,list) else len(d.get('embedding',[])))" 2>/dev/null) || _dm=0
        if [ "$_dm" -ge 384 ]; then echo "  ✓ Embeddings: $_dm dimensions"; _ok=$((_ok+1))
        else echo "  ✗ Wrong dimensions: $_dm"; _ko=$((_ko+1)); fi
    else echo "  ✗ Embeddings not working"; _ko=$((_ko+1)); fi

    echo "  [Python]"
    if PYTHONPATH="$INSTALL_DIR/src" "$_vp" -c "
import sys; sys.path.insert(0,'$INSTALL_DIR/src')
from shared.env_loader import load_env; load_env()
import importlib.util
spec=importlib.util.spec_from_file_location('u','$INSTALL_DIR/src/unified/server/main.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(f'  ✓ Unified: {len(m.mcp._tool_manager._tools)} tools, {len(m._loaded)} modules')
" 2>/dev/null; then _ok=$((_ok+1))
    else echo "  ✗ Unified server failed"; _ko=$((_ko+1)); fi

    echo ""
    if [ "$_ko" -eq 0 ]; then echo "  ✅ All checks passed ($_ok)"; else echo "  ⚠ $_ko checks failed ($_ok passed)"; fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ✓ Installation Complete                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Location: $INSTALL_DIR"
echo "  Config:   $INSTALL_DIR/config/mcp.json"
echo "  llama.cpp: Compiled from source → engine/bin/"
if [ "$(uname)" = "Darwin" ]; then
    echo "  GPU:       Metal enabled"
fi
echo "  Services:  Qdrant (6333) + llama-server ($LLAMA_PORT)"
echo "  To test:   cp $INSTALL_DIR/config/mcp.json ~/.pi/mcp.json"
echo ""
