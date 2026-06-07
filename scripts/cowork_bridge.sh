#!/bin/bash
# cowork_bridge.sh — Cowork auto-memory → inbox/ producer (repair plan P1).
#
# Copies new/changed .md memory files from the Claude Cowork auto-memory
# directory into <repo>/inbox/ with a "cowork-memory-" prefix. The backpack
# inbox scanner ingests them and archives to inbox/processed/.
#
# Triggered by launchd WatchPaths (com.agent-memory.cowork-bridge) on every
# change in the Cowork memory dir; also safe to run manually.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

COWORK_MEMORY_DIR="${COWORK_MEMORY_DIR:-/Users/ruben/Library/Application Support/Claude/local-agent-mode-sessions/3b2bb955-5100-45f9-bfcd-bde0ad6e444d/e790cca3-a832-461d-b87d-fc1ca403d911/spaces/59c9d747-6d76-4f2e-bbee-8dfca386aaff/memory}"
INBOX="$PROJECT_ROOT/inbox"
PROCESSED="$INBOX/processed"
PREFIX="cowork-memory-"

[ -d "$COWORK_MEMORY_DIR" ] || { echo "[cowork-bridge] memory dir not found: $COWORK_MEMORY_DIR" >&2; exit 0; }
mkdir -p "$INBOX" "$PROCESSED"

copied=0
shopt -s nullglob
for f in "$COWORK_MEMORY_DIR"/*.md; do
    base="$PREFIX$(basename "$f")"
    # Skip if an already-processed copy is at least as new as the source
    # (rsync -au preserves mtime, so this survives the inbox -> processed move).
    if [ -f "$PROCESSED/$base" ] && [ ! "$f" -nt "$PROCESSED/$base" ]; then
        continue
    fi
    rsync -au "$f" "$INBOX/$base"
    copied=$((copied + 1))
done

echo "[cowork-bridge] $(date '+%Y-%m-%dT%H:%M:%S') synced $copied file(s) into inbox/"
