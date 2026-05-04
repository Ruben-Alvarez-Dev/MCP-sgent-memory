#!/bin/bash
# update.sh - Update installation preserving data
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname $0)" && pwd)"
INSTALL_DIR="${1:-$HOME/MCP-servers/MCP-agent-memory}"
SOURCE_DIR="${2:-$SCRIPT_DIR}"
ERRORS=0

echo "=== Step 1: Detect mode ==="
source $SCRIPT_DIR/detect.sh $INSTALL_DIR
echo "  Mode: $MODE"
echo "  Data: $DETECT_HAS_DATA"

if [ "$DETECT_HAS_DATA" = true ]; then
  echo "=== Step 2: Backup ==="
  bash $SCRIPT_DIR/backup.sh $INSTALL_DIR || exit 1
fi

echo "=== Step 3: Stop services ==="
bash $SCRIPT_DIR/../install/services.sh $INSTALL_DIR 6333 stop 8081 2>/dev/null || true
sleep 2

echo "=== Step 4: Update code ==="
if [ -d "$SOURCE_DIR/src" ]; then
  cp -a $SOURCE_DIR/src $INSTALL_DIR/
  echo "  Updated src/"
fi
if [ -d "$SOURCE_DIR/install" ]; then
  mkdir -p $INSTALL_DIR/install
  for f in detect.sh backup.sh update.sh services.sh verify.sh config.sh deps.sh manifest.json; do
    [ -f "$SOURCE_DIR/install/$f" ] && cp "$SOURCE_DIR/install/$f" "$INSTALL_DIR/install/"
  done
  echo "  Updated install/"
fi
echo "  Preserved: data/, Lx-persistent/, models/, engine/"

echo "=== Step 5: Merge config ==="
if [ -f "$INSTALL_DIR/config/.env" ]; then
  EXISTING=$(grep -c = "$INSTALL_DIR/config/.env" 2>/dev/null || echo 0)
  echo "  Preserved .env ($EXISTING vars)"
elif [ -f "$INSTALL_DIR/etc/.env" ]; then
  # Migrate from legacy etc/ location
  mkdir -p "$INSTALL_DIR/config"
  cp "$INSTALL_DIR/etc/.env" "$INSTALL_DIR/config/.env"
  EXISTING=$(grep -c = "$INSTALL_DIR/config/.env" 2>/dev/null || echo 0)
  echo "  Migrated .env from etc/ → config/ ($EXISTING vars)"
else
  bash $SCRIPT_DIR/config.sh $INSTALL_DIR
fi

echo "=== Step 6: Update deps ==="
if [ -d "$INSTALL_DIR/.venv" ]; then
  $INSTALL_DIR/.venv/bin/pip install -q --upgrade mcp pydantic httpx pyyaml 2>/dev/null || true
  echo "  Updated deps"
fi

echo "=== Step 7: Start services ==="
bash $SCRIPT_DIR/../install/services.sh $INSTALL_DIR 6333 start 8081
sleep 5

echo "=== Step 8: Verify ==="
bash $SCRIPT_DIR/../install/verify.sh $INSTALL_DIR 2>/dev/null || ERRORS=$((ERRORS+1))

echo ""
if [ $ERRORS -eq 0 ]; then
  echo "  UPDATE SUCCESSFUL"
else
  echo "  UPDATE COMPLETED WITH "$ERRORS" WARNINGS"
fi
echo "  Dir: $INSTALL_DIR"
exit $ERRORS
