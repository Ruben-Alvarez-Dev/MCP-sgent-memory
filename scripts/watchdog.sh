#!/bin/bash
# watchdog.sh — Auto-recovery script for MCP Memory Server
#
# Checks all services and restarts dead ones via launchctl.
# Designed to run from cron or launchd every 5 minutes.
#
# Usage:
#   ./watchdog.sh              # Check and restart
#   ./watchdog.sh --dry-run    # Check only, no restart
#   ./watchdog.sh --status     # Show detailed status
#
# Cron example:
#   */5 * * * * /path/to/MCP-memory-server/scripts/watchdog.sh >> /tmp/memory-watchdog.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
export PYTHONPATH="${PROJECT_ROOT}/src"
export MEMORY_SERVER_DIR="${PROJECT_ROOT}"
export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
export LLAMA_SERVER_URL="${LLAMA_SERVER_URL:-http://127.0.0.1:8081}"

DRY_RUN=false
STATUS_ONLY=false
LOG_TAG="watchdog"

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --status) STATUS_ONLY=true ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${LOG_TAG}] $*"; }

restart_service() {
    local label="$1"
    local service_name="$2"
    
    if $DRY_RUN; then
        log "DRY RUN: would restart $service_name ($label)"
        return 0
    fi
    
    log "Restarting $service_name ($label)..."
    launchctl kickstart -k "gui/$(id -u)/$label" 2>/dev/null && \
        log "✅ $service_name restarted" || \
        log "❌ Failed to restart $service_name"
}

# ── Status mode ─────────────────────────────────────────────────────

if $STATUS_ONLY; then
    "$PYTHON" -m shared.health --json 2>/dev/null || \
        "$PYTHON" -m shared.health 2>/dev/null
    echo ""
    echo "=== Launchd Services ==="
    launchctl list | grep memory || echo "No memory services found"
    exit 0
fi

# ── Health check ────────────────────────────────────────────────────

log "Running health check..."

HEALTH_JSON=$("$PYTHON" -m shared.health --json 2>/dev/null) || true

if [ -z "$HEALTH_JSON" ]; then
    log "❌ Health check failed to produce output"
    log "Attempting to restart all services..."
    restart_service "com.memory-server.qdrant" "Qdrant"
    restart_service "com.memory-server.llama-embedding" "llama-server"
    restart_service "com.memory-server.gateway" "Gateway"
    exit 1
fi

# Parse results
OVERALL=$(echo "$HEALTH_JSON" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['overall_healthy'])" 2>/dev/null || echo "False")

if [ "$OVERALL" = "True" ]; then
    log "✅ All services healthy"
    exit 0
fi

# ── Individual service recovery ─────────────────────────────────────

log "⚠️  Some services unhealthy, checking individually..."

# Parse unhealthy services
UNHEALTHY=$("$PYTHON" -c "
import sys, json
health = json.loads('''$HEALTH_JSON''')
for svc in health['services']:
    if not svc['healthy']:
        print(svc['name'])
" 2>/dev/null || echo "")

for svc in $UNHEALTHY; do
    case "$svc" in
        qdrant)
            log "🔴 Qdrant is down"
            restart_service "com.memory-server.qdrant" "Qdrant"
            ;;
        llama-server)
            log "🔴 llama-server is down"
            restart_service "com.memory-server.llama-embedding" "llama-server"
            ;;
        gateway)
            log "🔴 Gateway is down"
            restart_service "com.memory-server.gateway" "Gateway"
            ;;
        embedding)
            log "🔴 Embedding pipeline degraded (circuit breaker may be open)"
            log "   This usually means llama-server is down. Restarting..."
            restart_service "com.memory-server.llama-embedding" "llama-server"
            ;;
        launchd)
            log "⚠️  Some launchd services not running"
            # Reload plists
            for plist in ~/Library/LaunchAgents/com.memory-server.*.plist; do
                if [ -f "$plist" ]; then
                    label=$(basename "$plist" .plist)
                    PID=$(launchctl list | grep "$label" | awk '{print $1}' 2>/dev/null || echo "-")
                    if [ "$PID" = "-" ]; then
                        log "   Loading $label..."
                        launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null || true
                    fi
                fi
            done
            ;;
        *)
            log "🔴 Unknown service: $svc"
            ;;
    esac
done

# ── Post-recovery verification ──────────────────────────────────────

sleep 5

POST_JSON=$("$PYTHON" -m shared.health --json 2>/dev/null) || true
if [ -n "$POST_JSON" ]; then
    POST_OVERALL=$(echo "$POST_JSON" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['overall_healthy'])" 2>/dev/null || echo "False")
    if [ "$POST_OVERALL" = "True" ]; then
        log "✅ Recovery successful — all services healthy"
        exit 0
    fi
fi

log "⚠️  Recovery incomplete — some services still unhealthy"
$DRY_RUN || "$PYTHON" -m shared.health 2>/dev/null
exit 1
