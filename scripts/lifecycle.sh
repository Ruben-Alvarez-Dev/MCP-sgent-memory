#!/bin/bash
# lifecycle.sh — Data lifecycle management for MCP Memory Server
#
# Handles: JSONL rotation, old thinking sessions cleanup, Qdrant backup,
#          stale staging files, heartbeat/reminders pruning.
#
# Usage:
#   ./scripts/lifecycle.sh                # Run all cleanup tasks
#   ./scripts/lifecycle.sh --dry-run      # Preview what would be cleaned
#   ./scripts/lifecycle.sh --backup       # Only Qdrant backup
#   ./scripts/lifecycle.sh --status       # Show data stats
#
# Cron (weekly):
#   0 3 * * 0 /path/to/MCP-agent-memory/scripts/lifecycle.sh >> ~/.memory/lifecycle.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configurable limits (env overrides)
JSONL_MAX_LINES="${JSONL_MAX_LINES:-10000}"          # Keep last N lines
THOUGHTS_MAX_AGE_DAYS="${THOUGHTS_MAX_AGE_DAYS:-30}"  # Delete sessions older than N days
STAGING_MAX_AGE_HOURS="${STAGING_MAX_AGE_HOURS:-168}"  # 7 days
HEARTBEATS_MAX_AGE_DAYS="${HEARTBEATS_MAX_AGE_DAYS:-7}"
REMINDERS_MAX_AGE_DAYS="${REMINDERS_MAX_AGE_DAYS:-90}"
QDRANT_BACKUP_KEEP="${QDRANT_BACKUP_KEEP:-3}"          # Keep last N snapshots
VAULT_MAX_AGE_DAYS="${VAULT_MAX_AGE_DAYS:-90}"

DRY_RUN=false
BACKUP_ONLY=false
STATUS_ONLY=false
DATA_DIR="${PROJECT_ROOT}/data"

for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=true ;;
        --backup|-b)  BACKUP_ONLY=true ;;
        --status|-s)  STATUS_ONLY=true ;;
    esac
done

G="\033[32m" R="\033[31m" Y="\033[33m" B="\033[1m" X="\033[0m"
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { echo "  ${G}✅ $*${X}"; }
warn() { echo "  ${Y}⚠️  $*${X}"; }
skip() { echo "  ⏭️  $*"; }

# ── Status mode ─────────────────────────────────────────────────────

if $STATUS_ONLY; then
    echo "${B}📊 Data Lifecycle Status${X}"
    echo ""
    
    # JSONL
    JSONL="$DATA_DIR/raw_events.jsonl"
    if [ -f "$JSONL" ]; then
        LINES=$(wc -l < "$JSONL" | tr -d ' ')
        SIZE=$(du -sh "$JSONL" | cut -f1 | tr -d ' ')
        echo "  📝 Events JSONL:    ${LINES} lines, ${SIZE} (max: ${JSONL_MAX_LINES})"
    fi
    
    # Thoughts
    THOUGHTS="$DATA_DIR/memory/thoughts"
    if [ -d "$THOUGHTS" ]; then
        COUNT=$(find "$THOUGHTS" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$THOUGHTS" 2>/dev/null | cut -f1 | tr -d ' ')
        OLDEST=$(find "$THOUGHTS" -name "*.json" -exec stat -f %B {} \; 2>/dev/null | sort -n | head -1)
        if [ -n "$OLDEST" ]; then
            OLDEST_DATE=$(date -r "$OLDEST" '+%Y-%m-%d' 2>/dev/null || echo "unknown")
            echo "  🧠 Thinking sessions: ${COUNT} files, ${SIZE} (oldest: ${OLDEST_DATE}, max age: ${THOUGHTS_MAX_AGE_DAYS}d)"
        else
            echo "  🧠 Thinking sessions: ${COUNT} files, ${SIZE}"
        fi
    fi
    
    # Staging
    STAGING="$DATA_DIR/staging_buffer"
    if [ -d "$STAGING" ]; then
        COUNT=$(find "$STAGING" -type f 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$STAGING" 2>/dev/null | cut -f1 | tr -d ' ')
        echo "  📦 Staging buffer:   ${COUNT} files, ${SIZE} (max age: ${STAGING_MAX_AGE_HOURS}h)"
    fi
    
    # Heartbeats
    HB="$DATA_DIR/memory/heartbeats"
    if [ -d "$HB" ]; then
        COUNT=$(find "$HB" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$HB" 2>/dev/null | cut -f1 | tr -d ' ')
        echo "  💓 Heartbeats:       ${COUNT} files, ${SIZE} (max age: ${HEARTBEATS_MAX_AGE_DAYS}d)"
    fi
    
    # Reminders
    REM="$DATA_DIR/memory/reminders"
    if [ -d "$REM" ]; then
        COUNT=$(find "$REM" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$REM" 2>/dev/null | cut -f1 | tr -d ' ')
        echo "  🔔 Reminders:        ${COUNT} files, ${SIZE} (max age: ${REMINDERS_MAX_AGE_DAYS}d)"
    fi
    
    # Qdrant
    QDRANT="$PROJECT_ROOT/src/shared/qdrant/data"
    if [ -d "$QDRANT" ]; then
        SIZE=$(du -sh "$QDRANT" 2>/dev/null | cut -f1 | tr -d ' ')
        SNAPSHOTS=$(find "$PROJECT_ROOT/src/shared/qdrant/snapshots" -name "*.snapshot" 2>/dev/null | wc -l | tr -d ' ')
        echo "  🗄️  Qdrant:           ${SIZE} (${SNAPSHOTS} snapshots, keep: ${QDRANT_BACKUP_KEEP})"
    fi
    
    # Engram
    ENG="$DATA_DIR/memory/engram"
    if [ -d "$ENG" ]; then
        COUNT=$(find "$ENG" -name "*.json" -o -name "*.yaml" 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$ENG" 2>/dev/null | cut -f1 | tr -d ' ')
        echo "  🏛️  Engram:           ${COUNT} files, ${SIZE}"
    fi
    
    # Vault
    VLT="$DATA_DIR/vault"
    if [ -d "$VLT" ]; then
        COUNT=$(find "$VLT" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
        SIZE=$(du -sh "$VLT" 2>/dev/null | cut -f1 | tr -d ' ')
        echo "  📓 Vault:             ${COUNT} files, ${SIZE} (max age: ${VAULT_MAX_AGE_DAYS}d)"
    fi
    
    # Total
    TOTAL=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 | tr -d ' ')
    echo ""
    echo "  ${B}Total: ${TOTAL}${X}"
    exit 0
fi

# ── Backup mode ─────────────────────────────────────────────────────

if $BACKUP_ONLY; then
    log "${B}📦 Qdrant Backup${X}"
    SNAP_DIR="$PROJECT_ROOT/src/shared/qdrant/snapshots"
    mkdir -p "$SNAP_DIR"
    
    # Create snapshot via API
    SNAP_NAME="auto-$(date '+%Y%m%d-%H%M%S')"
    RESULT=$(curl -s -X POST "http://127.0.0.1:6333/snapshots" \
        -H "Content-Type: application/json" \
        -d "{\"snapshot_name\": \"$SNAP_NAME\"}" 2>/dev/null || echo '{"error": "Qdrant not reachable"}')
    
    if echo "$RESULT" | grep -q '"ok"'; then
        ok "Snapshot created: $SNAP_NAME"
    else
        warn "Snapshot failed: $RESULT"
    fi
    
    # Rotate old snapshots
    COUNT=$(find "$SNAP_DIR" -name "*.snapshot" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$COUNT" -gt "$QDRANT_BACKUP_KEEP" ]; then
        REMOVE=$((COUNT - QDRANT_BACKUP_KEEP))
        find "$SNAP_DIR" -name "*.snapshot" -type f | sort | head -n "$REMOVE" | while read f; do
            if $DRY_RUN; then
                log "DRY RUN: would remove $(basename "$f")"
            else
                rm -f "$f"
                log "Removed old snapshot: $(basename "$f")"
            fi
        done
        ok "Rotated ${REMOVE} old snapshots"
    else
        skip "Snapshot rotation: ${COUNT}/${QDRANT_BACKUP_KEEP} — no cleanup needed"
    fi
    exit 0
fi

# ── Full lifecycle ──────────────────────────────────────────────────

log "${B}🧹 Data Lifecycle Management${X}"

TOTAL_FREED=0

# 1. JSONL Rotation
log "📝 JSONL Rotation (max ${JSONL_MAX_LINES} lines)"
JSONL="$DATA_DIR/raw_events.jsonl"
if [ -f "$JSONL" ]; then
    LINES=$(wc -l < "$JSONL" | tr -d ' ')
    if [ "$LINES" -gt "$JSONL_MAX_LINES" ]; then
        REMOVE=$((LINES - JSONL_MAX_LINES))
        if $DRY_RUN; then
            log "DRY RUN: would trim ${REMOVE} lines from ${LINES}"
        else
            # Keep last N lines
            tail -n "$JSONL_MAX_LINES" "$JSONL" > "$JSONL.tmp" && mv "$JSONL.tmp" "$JSONL"
            ok "Trimmed ${REMOVE} lines (${LINES} → ${JSONL_MAX_LINES})"
        fi
    else
        skip "JSONL: ${LINES}/${JSONL_MAX_LINES} lines — no rotation needed"
    fi
else
    skip "JSONL: file not found"
fi

# 2. Thinking Sessions Cleanup
log "🧠 Thinking Sessions (max age: ${THOUGHTS_MAX_AGE_DAYS}d)"
THOUGHTS="$DATA_DIR/memory/thoughts"
if [ -d "$THOUGHTS" ]; then
    CUTOFF=$(date -v-"${THOUGHTS_MAX_AGE_DAYS}"d '+%s' 2>/dev/null || date -d "${THOUGHTS_MAX_AGE_DAYS} days ago" '+%s' 2>/dev/null || echo 0)
    REMOVED=0
    find "$THOUGHTS" -name "*.json" -type f | while read f; do
        MTIME=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 9999999999)
        if [ "$MTIME" -lt "$CUTOFF" ] 2>/dev/null; then
            if $DRY_RUN; then
                log "DRY RUN: would remove $(basename "$f")"
            else
                rm -f "$f"
            fi
            REMOVED=$((REMOVED + 1))
        fi
    done
    if [ "$REMOVED" -gt 0 ]; then
        ok "Removed ${REMOVED} old thinking sessions"
    else
        skip "No old thinking sessions to clean"
    fi
else
    skip "Thinking sessions: directory not found"
fi

# 3. Staging Buffer Cleanup
log "📦 Staging Buffer (max age: ${STAGING_MAX_AGE_HOURS}h)"
STAGING="$DATA_DIR/staging_buffer"
if [ -d "$STAGING" ]; then
    CUTOFF=$(date -v-"${STAGING_MAX_AGE_HOURS}"H '+%s' 2>/dev/null || echo 0)
    REMOVED=0
    find "$STAGING" -type f | while read f; do
        MTIME=$(stat -f %m "$f" 2>/dev/null || echo 9999999999)
        if [ "$MTIME" -lt "$CUTOFF" ] 2>/dev/null; then
            if $DRY_RUN; then
                log "DRY RUN: would remove $(basename "$f")"
            else
                rm -f "$f"
            fi
            REMOVED=$((REMOVED + 1))
        fi
    done
    if [ "$REMOVED" -gt 0 ]; then
        ok "Removed ${REMOVED} old staging files"
    else
        skip "No old staging files to clean"
    fi
else
    skip "Staging buffer: directory not found"
fi

# 4. Heartbeats Cleanup
log "💓 Heartbeats (max age: ${HEARTBEATS_MAX_AGE_DAYS}d)"
HB="$DATA_DIR/memory/heartbeats"
if [ -d "$HB" ]; then
    CUTOFF=$(date -v-"${HEARTBEATS_MAX_AGE_DAYS}"d '+%s' 2>/dev/null || echo 0)
    REMOVED=0
    find "$HB" -name "*.json" -type f | while read f; do
        MTIME=$(stat -f %m "$f" 2>/dev/null || echo 9999999999)
        if [ "$MTIME" -lt "$CUTOFF" ] 2>/dev/null; then
            if $DRY_RUN; then
                log "DRY RUN: would remove $(basename "$f")"
            else
                rm -f "$f"
            fi
            REMOVED=$((REMOVED + 1))
        fi
    done
    if [ "$REMOVED" -gt 0 ]; then
        ok "Removed ${REMOVED} old heartbeat files"
    else
        skip "No old heartbeats to clean"
    fi
else
    skip "Heartbeats: directory not found"
fi

# 5. Reminders Cleanup (dismissed only)
log "🔔 Reminders (pruning dismissed older than ${REMINDERS_MAX_AGE_DAYS}d)"
REM="$DATA_DIR/memory/reminders"
if [ -d "$REM" ]; then
    REMOVED=0
    find "$REM" -name "*.json" -type f | while read f; do
        # Only prune dismissed reminders
        if grep -q '"dismissed"' "$f" 2>/dev/null || grep -q '"completed"' "$f" 2>/dev/null; then
            CUTOFF=$(date -v-"${REMINDERS_MAX_AGE_DAYS}"d '+%s' 2>/dev/null || echo 0)
            MTIME=$(stat -f %m "$f" 2>/dev/null || echo 9999999999)
            if [ "$MTIME" -lt "$CUTOFF" ] 2>/dev/null; then
                if $DRY_RUN; then
                    log "DRY RUN: would remove dismissed $(basename "$f")"
                else
                    rm -f "$f"
                fi
                REMOVED=$((REMOVED + 1))
            fi
        fi
    done
    if [ "$REMOVED" -gt 0 ]; then
        ok "Removed ${REMOVED} dismissed reminders"
    else
        skip "No dismissed reminders to prune"
    fi
else
    skip "Reminders: directory not found"
fi

# 6. Qdrant Backup
log "🗄️  Qdrant Backup"
SNAP_DIR="$PROJECT_ROOT/src/shared/qdrant/snapshots"
mkdir -p "$SNAP_DIR"
SNAP_NAME="auto-$(date '+%Y%m%d-%H%M%S')"
RESULT=$(curl -s -X POST "http://127.0.0.1:6333/snapshots" \
    -H "Content-Type: application/json" \
    -d "{\"snapshot_name\": \"$SNAP_NAME\"}" 2>/dev/null || echo '{"error": "Qdrant not reachable"}')

if echo "$RESULT" | grep -q '"ok"'; then
    ok "Snapshot created: $SNAP_NAME"
else
    warn "Snapshot failed (Qdrant may be down): $RESULT"
fi

# Rotate old snapshots
SNAP_COUNT=$(find "$SNAP_DIR" -name "*.snapshot" 2>/dev/null | wc -l | tr -d ' ')
if [ "$SNAP_COUNT" -gt "$QDRANT_BACKUP_KEEP" ]; then
    REMOVE=$((SNAP_COUNT - QDRANT_BACKUP_KEEP))
    find "$SNAP_DIR" -name "*.snapshot" -type f | sort | head -n "$REMOVE" | while read f; do
        if $DRY_RUN; then
            log "DRY RUN: would remove snapshot $(basename "$f")"
        else
            rm -f "$f"
            log "Removed old snapshot: $(basename "$f")"
        fi
    done
    ok "Rotated ${REMOVE} old snapshots"
else
    skip "Snapshots: ${SNAP_COUNT}/${QDRANT_BACKUP_KEEP} — no rotation needed"
fi

# ── Summary ─────────────────────────────────────────────────────────
TOTAL_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 | tr -d ' ')
QDRANT_SIZE=$(du -sh "$PROJECT_ROOT/src/shared/qdrant/data" 2>/dev/null | cut -f1 | tr -d ' ')
echo ""
log "${B}═══════════════════════════════════════════${X}"
log "${G}✅ Lifecycle complete${X}"
echo "  Data dir:   ${TOTAL_SIZE}"
echo "  Qdrant:     ${QDRANT_SIZE}"
echo "  Config:"
echo "    JSONL max:       ${JSONL_MAX_LINES} lines"
echo "    Thoughts max:    ${THOUGHTS_MAX_AGE_DAYS} days"
echo "    Staging max:     ${STAGING_MAX_AGE_HOURS} hours"
echo "    Heartbeats max:  ${HEARTBEATS_MAX_AGE_DAYS} days"
echo "    Snapshots keep:  ${QDRANT_BACKUP_KEEP}"
log "${B}═══════════════════════════════════════════${X}"
