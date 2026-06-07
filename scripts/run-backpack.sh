#!/bin/bash
# run-backpack.sh — launchd entry point for the Backpack daemon.
# Runs the smoke gate first; refuses to start broken code (the F-01
# NameError would have been caught here on day one). The sleep throttles
# launchd KeepAlive respawns while the tree is broken.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if ! "$PROJECT_ROOT/scripts/smoke.sh"; then
    echo "[run-backpack] SMOKE GATE FAILED — refusing to start the daemon" >&2
    sleep 30
    exit 1
fi

exec "$PROJECT_ROOT/.venv/bin/python" -u "$PROJECT_ROOT/src/unified/server/backpack.py"
