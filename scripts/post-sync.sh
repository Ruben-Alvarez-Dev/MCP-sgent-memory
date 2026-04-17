#!/usr/bin/env bash
# post-sync.sh — Redirects engram and context7 MCP configs to memory-server facade/proxy.
#
# Run this AFTER `gentle-ai sync` or after any gentle-ai operation that
# overwrites opencode.json. It rewrites the "engram" and "context7" entries
# to point to the local facade/proxy servers instead of standalone binaries.
#
# Usage:
#   ./post-sync.sh              # Apply patches
#   ./post-sync.sh --check      # Check status without modifying
#   ./post-sync.sh --revert     # Revert to gentle-ai defaults
#
# Location: /Users/ruben/Code/__MEMORY__/PROJECT-Memory/PROJECT-memory/MCP-servers/scripts/
#
# IMPORTANT: The config keys "engram" and "context7" are PRESERVED so that
# tool names remain "engram_mem_save" and "context7_resolve-library-id" —
# exactly what gentle-ai's prompts expect.

set -euo pipefail

OPENCODE_JSON="$HOME/.config/opencode/opencode.json"
BACKUP="$OPENCODE_JSON.pre-facade-backup"

# ── Load paths from central .env ──────────────────────────────────
# Single source of truth: config/.env declares everything.

# Find the .env file
ENV_FILE=""
if [[ -n "${MEMORY_SERVER_DIR:-}" ]]; then
    ENV_FILE="$MEMORY_SERVER_DIR/config/.env"
elif [[ -f "$(dirname "$0")/../config/.env" ]]; then
    ENV_FILE="$(cd "$(dirname "$0")/../config" && pwd)/.env"
elif [[ -f "$HOME/.mcp-memory-server.env" ]]; then
    ENV_FILE="$HOME/.mcp-memory-server.env"
fi

# Load env vars (don't overwrite existing)
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        # Skip comments and empty lines
        [[ -z "$key" || "$key" == \#* ]] && continue
        # Remove quotes
        value="${value#\"}" && value="${value%\"}"
        value="${value#\'}" && value="${value%\'}"
        # Expand ~
        value="${value/\~/$HOME}"
        # Don't overwrite
        if [[ -z "${!key:-}" ]]; then
            export "$key=$value"
        fi
    done < "$ENV_FILE"
fi

# ── Paths (all derived from .env) ─────────────────────────────────

PROD_BASE="${MEMORY_SERVER_DIR:?Set MEMORY_SERVER_DIR in config/.env}"
PYTHON="${PYTHON_BIN:?Set PYTHON_BIN in config/.env}"

FACADE_SCRIPT="$PROD_BASE/servers/engram-facade/server/main.py"
PROXY_SCRIPT="$PROD_BASE/servers/context7-proxy/server/main.py"

# ── Functions ──────────────────────────────────────────────────────

check_prerequisites() {
    local missing=0

    if ! command -v jq &>/dev/null; then
        echo "❌ jq not found. Install: brew install jq"
        missing=1
    fi

    if [[ ! -f "$OPENCODE_JSON" ]]; then
        echo "❌ opencode.json not found at $OPENCODE_JSON"
        missing=1
    fi

    if [[ ! -f "$PYTHON" ]]; then
        echo "❌ Python not found at $PYTHON"
        missing=1
    fi

    # Check if facade/proxy exist in production
    if [[ ! -f "$FACADE_SCRIPT" ]]; then
        echo "⚠️  Facade not deployed to production yet: $FACADE_SCRIPT"
        echo "   Run: cp -r servers/engram-facade $PROD_BASE/servers/"
        missing=1
    fi

    if [[ ! -f "$PROXY_SCRIPT" ]]; then
        echo "⚠️  Proxy not deployed to production yet: $PROXY_SCRIPT"
        echo "   Run: cp -r servers/context7-proxy $PROD_BASE/servers/"
        missing=1
    fi

    return $missing
}

check_status() {
    echo "📋 Post-sync Status Check"
    echo "========================="

    if [[ ! -f "$OPENCODE_JSON" ]]; then
        echo "❌ opencode.json not found"
        return 1
    fi

    # Check engram config
    local engram_cmd
    engram_cmd=$(jq -r '.mcp.engram.command // .engram.command // "not-found"' "$OPENCODE_JSON" 2>/dev/null)

    if [[ "$engram_cmd" == *"$PYTHON"* ]] || [[ "$engram_cmd" == *"engram-facade"* ]]; then
        echo "✅ engram → facade (active)"
    elif [[ "$engram_cmd" == "not-found" ]]; then
        echo "⚠️  engram config not found in opencode.json"
    else
        echo "❌ engram → standalone binary ($engram_cmd)"
        echo "   Run: $0 to redirect to facade"
    fi

    # Check context7 config
    local ctx7_type
    ctx7_type=$(jq -r '.mcp.context7.type // .context7.type // "not-found"' "$OPENCODE_JSON" 2>/dev/null)

    local ctx7_cmd
    ctx7_cmd=$(jq -r '.mcp.context7.command[2] // ""' "$OPENCODE_JSON" 2>/dev/null)

    if [[ "$ctx7_cmd" == *"context7-proxy"* ]]; then
        echo "✅ context7 → proxy (active)"
    elif [[ "$ctx7_type" == "remote" ]]; then
        echo "❌ context7 → remote direct (needs redirect)"
    else
        echo "⚠️  context7 config: $ctx7_type"
    fi

    # Check backup
    if [[ -f "$BACKUP" ]]; then
        echo "📦 Backup exists: $BACKUP"
    fi
}

apply_patch() {
    echo "🔧 Patching opencode.json..."

    # Backup original
    cp "$OPENCODE_JSON" "$BACKUP"
    echo "📦 Backup: $BACKUP"

    # Patch engram: change command/args to point to facade
    # The JSON structure in opencode.json has MCP servers under the "mcp" key
    # but the engram/context7 entries are at the top level alongside "mcp"

    # We need to handle both possible structures:
    # 1. engram at top level (current opencode format)
    # 2. engram inside mcp object (some configs)

    local TMPFILE
    TMPFILE=$(mktemp)

    # Replace the engram and context7 entries
    # opencode.json uses: { "command": ["/path", "arg1", ...], "type": "local" }
    # IMPORTANT: opencode's schema does NOT accept "env" field in MCP configs.
    # So environment variables must be set by the scripts themselves.

    jq --arg python "$PYTHON" \
       --arg facade "$FACADE_SCRIPT" \
       --arg proxy "$PROXY_SCRIPT" '
        # Patch engram inside mcp (this is where gentle-ai puts it)
        if .mcp.engram then
            .mcp.engram = {
                "command": [$python, "-u", $facade],
                "type": "local"
            }
        else . end
        |
        # Patch engram at top level (fallback)
        if .engram then
            .engram = {
                "command": [$python, "-u", $facade],
                "type": "local"
            }
        else . end
        |
        # Patch context7 inside mcp (gentle-ai puts it here as remote)
        if .mcp.context7 then
            .mcp.context7 = {
                "command": [$python, "-u", $proxy],
                "type": "local"
            }
        else . end
        |
        # Patch context7 at top level (fallback)
        if .context7 then
            .context7 = {
                "command": [$python, "-u", $proxy],
                "type": "local"
            }
        else . end
    ' "$OPENCODE_JSON" > "$TMPFILE"

    # Validate the output
    if jq empty "$TMPFILE" 2>/dev/null; then
        mv "$TMPFILE" "$OPENCODE_JSON"
        echo "✅ Patched engram → facade"
        echo "✅ Patched context7 → proxy"
        echo ""
        echo "⚠️  Restart opencode for changes to take effect."
    else
        echo "❌ Generated JSON is invalid! Keeping original."
        rm "$TMPFILE"
        return 1
    fi
}

revert() {
    if [[ -f "$BACKUP" ]]; then
        cp "$BACKUP" "$OPENCODE_JSON"
        echo "✅ Reverted to backup: $BACKUP"
    else
        echo "❌ No backup found at $BACKUP"
        return 1
    fi
}

# ── Main ───────────────────────────────────────────────────────────

case "${1:-apply}" in
    --check|-c)
        check_status
        ;;
    --revert|-r)
        revert
        ;;
    --help|-h)
        echo "Usage: $0 [--check|--revert|--help]"
        echo ""
        echo "  (no args)  Apply facade/proxy patches to opencode.json"
        echo "  --check    Check current status without modifying"
        echo "  --revert   Restore pre-patch backup"
        echo "  --help     Show this help"
        ;;
    apply|*)
        if ! check_prerequisites; then
            echo ""
            echo "❌ Prerequisites not met. Fix the above and try again."
            exit 1
        fi
        apply_patch
        ;;
esac
