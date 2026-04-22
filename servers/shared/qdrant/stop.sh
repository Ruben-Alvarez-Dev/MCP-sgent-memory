#!/bin/bash
# Stop Qdrant vector store
pkill -f "qdrant" 2>/dev/null || echo "Qdrant not running."
