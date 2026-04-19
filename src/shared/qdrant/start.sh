#!/bin/bash
# Start Qdrant vector store — launchd-compatible wrapper
# Called by com.agent-memory.qdrant.plist
set -e

ulimit -n 10240 2>/dev/null || true
export MALLOC_CONF="background_thread:false,narenas:1"

cd "$(dirname "$0")"
mkdir -p data snapshots

exec ./qdrant --config-path config.yaml
