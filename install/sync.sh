#!/bin/bash
# sync.sh — Clean file synchronization between source and install directory
#
# Reads manifest.json from SOURCE to determine what should be installed (payload)
# and what must never be touched (preserve). Removes zombie files that exist in the
# install dir but not in the new source, then copies new/modified files over.
#
# Usage: sync.sh <source_dir> <install_dir>
# Env:   DRY_RUN=1  — print what would happen without executing
#
# Designed to be sourced by update.sh (functions are reusable).
#
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Defaults ─────────────────────────────────────────────────────────────────
SOURCE_DIR=""
INSTALL_DIR=""
DRY_RUN="${DRY_RUN:-0}"

# ── Helpers ──────────────────────────────────────────────────────────────────
log_green()  { echo -e "  ${GREEN}✓${RESET} $*"; }
log_yellow() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
log_red()    { echo -e "  ${RED}✗${RESET} $*"; }
log_dim()    { echo -e "  ${DIM}$*${RESET}"; }

# Resolve to absolute paths
abs_dir() {
    cd "$1" && pwd
}

# ── Read manifest from source directory ──────────────────────────────────────
# Exports: MANIFEST_PAYLOAD (newline-separated glob patterns)
#          MANIFEST_PRESERVE (newline-separated glob patterns)
#          MANIFEST_VERSION (string)
# Returns: 0 on success, 1 if manifest missing or invalid
read_manifest() {
    local manifest="$SOURCE_DIR/install/manifest.json"
    if [ ! -f "$manifest" ]; then
        return 1
    fi

    MANIFEST_VERSION=$(python3 -c "
import json, sys
try:
    m = json.load(open('$manifest'))
    print(m.get('version', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null || echo "unknown")

    MANIFEST_PAYLOAD=$(python3 -c "
import json
m = json.load(open('$manifest'))
for p in m.get('payload', []):
    print(p)
" 2>/dev/null || true)

    MANIFEST_PRESERVE=$(python3 -c "
import json
m = json.load(open('$manifest'))
for p in m.get('preserve', []):
    print(p)
" 2>/dev/null || true)

    # Validate we got at least some payload patterns
    if [ -z "$MANIFEST_PAYLOAD" ]; then
        return 1
    fi

    return 0
}

# ── Expand payload globs into a sorted list of relative file paths ───────────
# Uses python3 + pathlib.glob for proper ** support.
# Arguments: $1 = base directory to expand from
# Prints: one relative path per line (sorted), suitable for comparison
expand_payload_files() {
    local base="$1"
    python3 -c "
import json, os, sys
from pathlib import Path

base = Path('$base')
manifest = base / 'install' / 'manifest.json'
if not manifest.exists():
    sys.exit(1)

payload_patterns = json.loads('''$(echo "$MANIFEST_PAYLOAD" | python3 -c "
import sys, json
lines = [l.strip() for l in sys.stdin if l.strip()]
print(json.dumps(lines))
")''')

seen = set()
for pattern in payload_patterns:
    for p in sorted(base.glob(pattern)):
        if p.is_file():
            rel = p.relative_to(base)
            seen.add(str(rel))

for f in sorted(seen):
    print(f)
" 2>/dev/null
}

# ── List files currently in install dir under payload patterns ────────────────
# We scan the same payload patterns against the install dir to find what's there.
list_installed_payload_files() {
    local base="$1"
    python3 -c "
import json, os, sys
from pathlib import Path

base = Path('$base')
payload_patterns = json.loads('''$(echo "$MANIFEST_PAYLOAD" | python3 -c "
import sys, json
lines = [l.strip() for l in sys.stdin if l.strip()]
print(json.dumps(lines))
")''')

seen = set()
for pattern in payload_patterns:
    for p in sorted(base.glob(pattern)):
        if p.is_file():
            rel = p.relative_to(base)
            seen.add(str(rel))

for f in sorted(seen):
    print(f)
" 2>/dev/null
}

# ── Check if a relative path matches any preserve pattern ────────────────────
# Returns 0 (true) if the path SHOULD be preserved (not deleted)
# Returns 1 (false) if the path is safe to delete
matches_preserve() {
    local relpath="$1"
    local install_base="$2"

    if [ -z "$MANIFEST_PRESERVE" ]; then
        return 1  # no preserve patterns, safe to delete
    fi

    python3 -c "
import json, sys
from pathlib import PurePath

path = PurePath('$relpath')
preserve_patterns = json.loads('''$(echo "$MANIFEST_PRESERVE" | python3 -c "
import sys, json
lines = [l.strip() for l in sys.stdin if l.strip()]
print(json.dumps(lines))
")''')

for pattern in preserve_patterns:
    # Handle ** glob via fnmatch on each part
    if path.match(pattern):
        sys.exit(0)  # matches preserve → do NOT delete
    # Also check if the path is under a preserved directory prefix
    parts = pattern.rstrip('*').rstrip('/')
    if parts and str(path).startswith(parts + '/'):
        sys.exit(0)

sys.exit(1)  # does not match any preserve pattern
" 2>/dev/null
    return $?
}

# ── Copy files from source to install using rsync or cp fallback ─────────────
# Copies each expanded payload file, printing only a summary.
# Arguments: $1 = source_dir, $2 = install_dir, $3 = file list (newline-sep)
# Returns: count of copied files (new + updated)
copy_payload() {
    local src="$1"
    local dst="$2"
    local filelist="$3"
    local copied=0
    local added=0

    if [ -z "$filelist" ]; then
        echo "0 0"
        return 0
    fi

    # Build temp file list for rsync --files-from
    local tmp_list
    tmp_list=$(mktemp)
    echo "$filelist" > "$tmp_list"

    # Count new vs existing files, then copy (or pretend to)
    while IFS= read -r rel; do
        [ -z "$rel" ] && continue
        if [ ! -f "$dst/$rel" ]; then
            added=$((added + 1))
        fi
        copied=$((copied + 1))
    done < "$tmp_list"

    if [ "$DRY_RUN" != "1" ]; then
        if command -v rsync &>/dev/null; then
            rsync -a --files-from="$tmp_list" "$src/" "$dst/" 2>/dev/null
        else
            while IFS= read -r rel; do
                [ -z "$rel" ] && continue
                local target_dir="$dst/$(dirname "$rel")"
                [ -d "$target_dir" ] || mkdir -p "$target_dir"
                cp -a "$src/$rel" "$dst/$rel" 2>/dev/null || true
            done < "$tmp_list"
        fi
    fi

    rm -f "$tmp_list"
    echo "$copied $added"
}

# ── Main sync function ───────────────────────────────────────────────────────
# Can be called directly or sourced: do_sync <source_dir> <install_dir>
do_sync() {
    SOURCE_DIR="${1:?Usage: sync.sh <source_dir> <install_dir>}"
    INSTALL_DIR="${2:?Usage: sync.sh <source_dir> <install_dir>}"

    # Resolve to absolute paths
    SOURCE_DIR=$(abs_dir "$SOURCE_DIR")
    # INSTALL_DIR may not exist yet — resolve parent and append basename
    if [ -d "$INSTALL_DIR" ]; then
        INSTALL_DIR=$(abs_dir "$INSTALL_DIR")
    else
        local parent
        parent=$(cd "$(dirname "$INSTALL_DIR")" && pwd)
        INSTALL_DIR="$parent/$(basename "$INSTALL_DIR")"
    fi

    echo -e "── Sync: ${BOLD}$SOURCE_DIR${RESET} → ${BOLD}$INSTALL_DIR${RESET} ──"

    # ── Edge case: dev mode (same dir) ───────────────────────────────────
    if [ "$SOURCE_DIR" = "$INSTALL_DIR" ]; then
        log_dim "Source == Install (dev mode), skipping sync"
        return 0
    fi

    # ── Edge case: fresh install ─────────────────────────────────────────
    if [ ! -d "$INSTALL_DIR" ]; then
        echo "  Fresh install — creating $INSTALL_DIR"
        if [ "$DRY_RUN" = "1" ]; then
            log_dim "Would mkdir -p $INSTALL_DIR"
            return 0
        fi
        mkdir -p "$INSTALL_DIR"
        # Fall through to normal copy — no zombies possible
    fi

    # ── Read manifest ────────────────────────────────────────────────────
    if ! read_manifest; then
        log_yellow "No valid manifest.json in source — doing full copy (no zombie detection)"
        # Full copy without zombie detection
        local all_files
        all_files=$(find "$SOURCE_DIR" -type f -not -path '*/.git/*' \
            -printf '%P\n' 2>/dev/null | sort || true)
        local result
        result=$(copy_payload "$SOURCE_DIR" "$INSTALL_DIR" "$all_files")
        local total=${result%% *}
        local added=${result##* }
        if [ "$DRY_RUN" = "1" ]; then
            log_dim "Would copy $total files"
        else
            log_green "Copied $total files (fresh install)"
        fi
        return 0
    fi

    local manifest_version="${MANIFEST_VERSION:-unknown}"

    # ── Build file manifests ─────────────────────────────────────────────
    log_dim "Scanning payload..."
    local source_files
    source_files=$(expand_payload_files "$SOURCE_DIR")
    local source_count
    source_count=$(echo "$source_files" | grep -c . || true)
    echo "  Scanning payload... $source_count files in manifest (v$manifest_version)"

    local installed_files=""
    local installed_count=0
    if [ -d "$INSTALL_DIR" ]; then
        installed_files=$(list_installed_payload_files "$INSTALL_DIR")
        installed_count=$(echo "$installed_files" | grep -c . || true)
    fi
    echo "  Scanning install... $installed_count files present"

    # ── Detect and remove zombies ────────────────────────────────────────
    local zombie_count=0
    local preserved_count=0

    # Files in install but NOT in source = zombies
    if [ -n "$installed_files" ] && [ -n "$source_files" ]; then
        local zombies
        zombies=$(comm -23 <(echo "$installed_files") <(echo "$source_files") || true)

        if [ -n "$zombies" ]; then
            while IFS= read -r zombie; do
                [ -z "$zombie" ] && continue

                # ── Preserve check — NEVER delete preserved paths ────────
                if matches_preserve "$zombie" "$INSTALL_DIR"; then
                    if [ "$DRY_RUN" = "1" ]; then
                        log_dim "Would preserve $zombie (matches preserve pattern)"
                    fi
                    preserved_count=$((preserved_count + 1))
                    continue
                fi

                zombie_count=$((zombie_count + 1))
                if [ "$zombie_count" -eq 1 ]; then
                    echo "  Zombies: found stale files"
                fi
                log_yellow "Removing $zombie (not in v$manifest_version)"
                if [ "$DRY_RUN" != "1" ]; then
                    rm -f "$INSTALL_DIR/$zombie" 2>/dev/null || true
                fi
            done <<< "$zombies"
        fi
    fi

    if [ "$zombie_count" -gt 0 ]; then
        echo "  Zombies: $zombie_count files removed"
    else
        log_dim "Zombies: none detected"
    fi

    # ── Show what was preserved ──────────────────────────────────────────
    local preserve_summary=""
    for pattern in $MANIFEST_PRESERVE; do
        preserve_summary="$preserve_summary ${pattern%/**}/,"
    done
    if [ -n "$preserve_summary" ]; then
        preserve_summary=$(echo "$preserve_summary" | sed 's/^ //' | sed 's/,$//')
        log_dim "Preserved: $preserve_summary"
    fi

    # ── Copy new/modified files ──────────────────────────────────────────
    local result
    result=$(copy_payload "$SOURCE_DIR" "$INSTALL_DIR" "$source_files")
    local total_copied=${result%% *}
    local total_added=${result##* }
    local total_updated=$((total_copied - total_added))

    if [ "$total_copied" -gt 0 ]; then
        if [ "$DRY_RUN" = "1" ]; then
            log_dim "Would update: $total_updated changed, $total_added added"
        else
            log_green "Updated: $total_updated files changed, $total_added files added"
        fi
    fi

    # ── Done ─────────────────────────────────────────────────────────────
    echo -e "  ${GREEN}✓${RESET} Sync complete: v$manifest_version ($source_count files)"
}

# ── Entry point (only when run directly, not sourced) ─────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    do_sync "$@"
fi
