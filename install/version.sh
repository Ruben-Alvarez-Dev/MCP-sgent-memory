#!/bin/bash
# version.sh - Version detection, comparison, and update checking
#
# Reads version from manifest.json (single source of truth), compares with
# GitHub releases API, and provides functions for other scripts to consume.
#
# Usage (CLI):
#   version.sh check [INSTALL_DIR]  — print version status
#   version.sh local [INSTALL_DIR]  — print local version
#   version.sh remote [INSTALL_DIR] — print remote version
#
# Usage (sourced):
#   source version.sh
#   get_local_version "/path/to/install"
#
# Default INSTALL_DIR: $HOME/MCP-servers/MCP-agent-memory
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"

# ── Helpers ───────────────────────────────────────────────────────────────────

_print_ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
_print_warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
_print_err()  { echo -e "  ${RED}✗${RESET} $*" >&2; }

# Strip an optional leading 'v' from a version tag (e.g. v2.1.0 → 2.1.0)
_strip_v() {
    local ver="${1:-}"
    echo "${ver#v}"
}

# ── Core functions ────────────────────────────────────────────────────────────

# Read the version field from manifest.json.
# Returns "0.0.0" if the file or field is missing.
get_local_version() {
    local install_dir="${1:-$HOME/MCP-servers/MCP-agent-memory}"
    local manifest="$install_dir/install/manifest.json"

    if [[ ! -f "$manifest" ]]; then
        echo "0.0.0"
        return 0
    fi

    local ver
    ver=$(python3 -c "
import json, sys
with open('$manifest') as f:
    data = json.load(f)
print(data.get('version', '0.0.0'))
" 2>/dev/null) || ver="0.0.0"

    echo "$(_strip_v "${ver:-0.0.0}")"
}

# Query GitHub releases API for the latest tag_name.
# Returns "" on any failure (network, parse, etc.).
get_remote_version() {
    local install_dir="${1:-$HOME/MCP-servers/MCP-agent-memory}"
    local manifest="$install_dir/install/manifest.json"

    # Determine owner/repo from manifest
    local repo
    if [[ -f "$manifest" ]]; then
        repo=$(python3 -c "
import json
with open('$manifest') as f:
    data = json.load(f)
print(data.get('repo', ''))
" 2>/dev/null) || repo=""
    fi

    if [[ -z "$repo" ]]; then
        echo "" >&2
        _print_err "No 'repo' field found in manifest.json"
        return 1
    fi

    local api_url="https://api.github.com/repos/${repo}/releases/latest"
    local response
    response=$(curl -fsSL --max-time 10 "$api_url" 2>/dev/null) || {
        echo ""
        return 0
    }

    local tag
    tag=$(echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('tag_name', ''))
" 2>/dev/null) || tag=""

    if [[ -n "$tag" ]]; then
        echo "$(_strip_v "$tag")"
    else
        echo ""
    fi
}

# Return the git-described version if inside a repo, else "".
get_git_version() {
    local ver
    ver=$(git describe --tags --always 2>/dev/null) || {
        echo ""
        return 0
    }
    echo "$(_strip_v "$ver")"
}

# Compare local vs remote version and print a human-readable summary.
# Returns one of: UP_TO_DATE | UPDATE_AVAILABLE | UNKNOWN
check_for_update() {
    local install_dir="${1:-$HOME/MCP-servers/MCP-agent-memory}"
    local local_ver remote_ver

    local_ver=$(get_local_version "$install_dir")
    remote_ver=$(get_remote_version "$install_dir") || true

    echo "── Version Check ──────────────────────"
    echo "  Local:  ${local_ver}"

    if [[ -z "$remote_ver" ]]; then
        echo "  Remote: ${DIM}unreachable${RESET}"
        _print_warn "Could not reach remote — skipping update check"
        echo "UNKNOWN"
        return 0
    fi

    echo "  Remote: v${remote_ver}"

    if [[ "$local_ver" == "$remote_ver" ]]; then
        _print_ok "Up to date (${local_ver})"
        echo "UP_TO_DATE"
        return 0
    fi

    # Simple string comparison: if remote != local, assume update available.
    # For a proper semver comparison, we sort and check.
    local greater
    greater=$(python3 -c "
from packaging.version import Version
v_local = Version('$local_ver')
v_remote = Version('$remote_ver')
print('remote' if v_remote > v_local else 'local')
" 2>/dev/null) || greater="local"

    if [[ "$greater" == "remote" ]]; then
        _print_warn "Update available: ${local_ver} → ${remote_ver}"
        echo "UPDATE_AVAILABLE"
    else
        _print_ok "Up to date (${local_ver})"
        echo "UP_TO_DATE"
    fi
}

# Write a new version string into manifest.json's version field.
# Usage: bump_manifest_version "2.1.0" [INSTALL_DIR]
bump_manifest_version() {
    local new_ver="${1:?Usage: bump_manifest_version VERSION [INSTALL_DIR]}"
    local install_dir="${2:-$HOME/MCP-servers/MCP-agent-memory}"
    local manifest="$install_dir/install/manifest.json"

    if [[ ! -f "$manifest" ]]; then
        _print_err "manifest.json not found at $manifest"
        return 1
    fi

    python3 -c "
import json
with open('$manifest', 'r') as f:
    data = json.load(f)
data['version'] = '$new_ver'
with open('$manifest', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"

    _print_ok "Version bumped to ${new_ver} in manifest.json"
}

# ── CLI interface (only when called directly, not sourced) ────────────────────

_cli_usage() {
    echo "Usage: version.sh <command> [INSTALL_DIR]"
    echo ""
    echo "Commands:"
    echo "  check   Compare local vs remote version"
    echo "  local   Print local version"
    echo "  remote  Print latest remote version"
    echo ""
    echo "Default INSTALL_DIR: \$HOME/MCP-servers/MCP-agent-memory"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    _CLI_DIR="${2:-$HOME/MCP-servers/MCP-agent-memory}"

    case "${1:-help}" in
        check)
            check_for_update "$_CLI_DIR"
            ;;
        local)
            get_local_version "$_CLI_DIR"
            ;;
        remote)
            get_remote_version "$_CLI_DIR"
            ;;
        help|--help|-h)
            _cli_usage
            ;;
        *)
            _print_err "Unknown command: $1"
            _cli_usage
            exit 1
            ;;
    esac
fi
