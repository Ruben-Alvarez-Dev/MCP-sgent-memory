#!/bin/bash
# Start Qdrant vector store
ulimit -n 10240
export MALLOC_CONF="background_thread:false,narenas:1"
cd "$(dirname "$0")"
mkdir -p data snapshots
exec ./qdrant --config-path config.yaml
