#!/bin/bash
# backup-data.sh — Daily automated snapshot of the memory corpus.
# Creates a verified tar.gz of data/ (excluding logs) with 7-day retention.
# Scheduled via launchd: com.agent-memory.backup (daily 04:00).
# Part of remediation Phase 7 (resilience & corpus hygiene), 2026-06-07.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-$HOME/MCP-servers/backups/auto}"
RETENTION=7

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$BACKUP_DIR/data-$STAMP.tar.gz"

tar -czf "$OUT" -C "$PROJECT_ROOT" --exclude='data/logs' data

# Verify the archive is readable before trusting it.
if ! tar -tzf "$OUT" > /dev/null 2>&1; then
    echo "[backup] ERROR: archive verification failed for $OUT" >&2
    rm -f "$OUT"
    exit 1
fi

SIZE=$(du -h "$OUT" | cut -f1)
echo "[backup] OK $OUT ($SIZE)"

# Retention: keep the newest $RETENTION archives.
ls -t "$BACKUP_DIR"/data-*.tar.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | while read -r old; do
    echo "[backup] pruning $old"
    rm -f "$old"
done
