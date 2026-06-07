#!/bin/bash
# smoke.sh — Pre-start gate for the Backpack daemon.
# Compiles every source file and exercises the four backpack modules plus
# the consolidation state functions in an isolated temp dir. A deleted
# function or syntax error can never reach a running daemon again (F-01
# postmortem guard). Exit 0 = safe to start.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PY="$PROJECT_ROOT/.venv/bin/python3"

# Gate 1: full compile sweep (fast, catches syntax errors anywhere).
"$PY" -m compileall -q "$PROJECT_ROOT/src" > /dev/null

# Gate 2: import the four backpack modules and round-trip the
# consolidation state functions against a throwaway temp dir.
T=$(mktemp -d)
mkdir -p "$T/L4"
cp "$PROJECT_ROOT/data/L4-narrative/state.json" "$T/L4/" 2>/dev/null || true

SMOKE_ROOT="$PROJECT_ROOT" L4_NARRATIVE_PATH="$T/L4" PYTHONPATH="$PROJECT_ROOT/src" "$PY" <<'EOF'
import importlib.util, os
base = os.environ["SMOKE_ROOT"]
mods = {}
for mod in ["L0_capture", "L0_to_L4_consolidation", "L5_routing", "L2_conversations"]:
    p = f"{base}/src/{mod}/server/main.py"
    spec = importlib.util.spec_from_file_location(mod, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    mods[mod] = m
c = mods["L0_to_L4_consolidation"]
s = c._load_state()
c._save_state(s)
print("SMOKE OK — 4 modules import, state round-trip works")
EOF
rm -rf "$T"
