#!/bin/bash
set -euo pipefail
INSTALL_DIR="$1"
if [ -z "$INSTALL_DIR" ]; then echo Usage; exit 1; fi
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR="$INSTALL_DIR/backups/$TIMESTAMP"
MAX_BACKUPS=5
BACKUP_SIZE=0
FILE_COUNT=0
mkdir -p "$BACKUP_DIR"
if [ -d "$INSTALL_DIR/data" ]; then
  mkdir -p "$BACKUP_DIR/data"
  cp -a "$INSTALL_DIR/data/." "$BACKUP_DIR/data/" 2>/dev/null || true
  SIZE=$(du -sk "$BACKUP_DIR/data" 2>/dev/null | cut -f1) || SIZE=0
  BACKUP_SIZE=$((BACKUP_SIZE + SIZE))
  COUNT=$(find "$BACKUP_DIR/data" -type f 2>/dev/null | wc -l | tr -d ' ')
  FILE_COUNT=$((FILE_COUNT + COUNT))
  echo OK-data
fi
if [ -d "$INSTALL_DIR/config" ]; then
  mkdir -p "$BACKUP_DIR/config"
  cp -a "$INSTALL_DIR/config/." "$BACKUP_DIR/config/" 2>/dev/null || true
  SIZE=$(du -sk "$BACKUP_DIR/config" 2>/dev/null | cut -f1) || SIZE=0
  BACKUP_SIZE=$((BACKUP_SIZE + SIZE))
  echo OK-config
fi
if [ -d "$INSTALL_DIR/vault" ] || [ -d "$INSTALL_DIR/data/Lx-persistent" ]; then
  mkdir -p "$BACKUP_DIR/vault"
  cp -a "$INSTALL_DIR/data/Lx-persistent/." "$BACKUP_DIR/vault/" 2>/dev/null || true
  SIZE=$(du -sk "$BACKUP_DIR/vault" 2>/dev/null | cut -f1) || SIZE=0
  BACKUP_SIZE=$((BACKUP_SIZE + SIZE))
  COUNT=$(find "$BACKUP_DIR/vault" -type f 2>/dev/null | wc -l | tr -d ' ')
  FILE_COUNT=$((FILE_COUNT + COUNT))
  echo OK-vault
fi
if [ -f "$INSTALL_DIR/install/manifest.json" ]; then
  mkdir -p "$BACKUP_DIR/install"
  cp "$INSTALL_DIR/install/manifest.json" "$BACKUP_DIR/install/"
fi
VERIFY_OK=true
if [ -d "$INSTALL_DIR/data" ] && [ -d "$BACKUP_DIR/data" ]; then
  SRC=$(find "$INSTALL_DIR/data" -type f 2>/dev/null | wc -l | tr -d ' ')
  BAK=$(find "$BACKUP_DIR/data" -type f 2>/dev/null | wc -l | tr -d ' ')
  if [ "$SRC" -gt 0 ] && [ "$BAK" -lt "$SRC" ]; then echo FAIL-verify; VERIFY_OK=false; fi
fi
BCOUNT=$(ls -1d "$INSTALL_DIR/backups"/*/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$BCOUNT" -gt "$MAX_BACKUPS" ]; then
  DEL=$((BCOUNT - MAX_BACKUPS))
  ls -1d "$INSTALL_DIR/backups"/*/ | head -"$DEL" | while read -r old; do rm -rf "$old"; done
fi
echo RESULT=$VERIFY_OK
if [ "$VERIFY_OK" = true ]; then echo OK; exit 0; else echo WARN; exit 1; fi
