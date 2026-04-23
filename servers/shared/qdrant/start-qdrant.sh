#!/bin/bash
ulimit -n 10240
export MALLOC_CONF="background_thread:false,narenas:1"
cd /Users/ruben/Code/PROJECT-Memory/project_MEMORY-after-A0/MCP-servers/shared/qdrant
exec ./qdrant --config-path config.yaml
