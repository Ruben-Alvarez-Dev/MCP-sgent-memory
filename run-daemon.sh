#!/bin/bash
# Daemon wrapper for unified MCP server
# Keeps stdin open for stdio transport via FIFO
cd "$(dirname "$0")"

FIFO=/tmp/mcp-server-stdin
rm -f "$FIFO"
mkfifo "$FIFO"

ulimit -n 65536

exec >>data/logs/unified.stdout.log 2>>data/logs/unified.stderr.log

echo "[$(date)] Starting unified server..."

# Start Python with FIFO as stdin (opens read end)
# AND open write end in same command to prevent deadlock
(
  exec 3>"$FIFO"   # Open write end (unblocks read end)
  while kill -0 $! 2>/dev/null; do sleep 60; done
) &
KEEPER_PID=$!

.venv/bin/python3 -u src/unified/server/main.py < "$FIFO" &
SERVER_PID=$!

echo "[$(date)] Started unified server PID=$SERVER_PID keeper=$KEEPER_PID"

# Wait for server to exit
wait $SERVER_PID
echo "[$(date)] Server exited with code $?"
exec 3>&- 2>/dev/null
rm -f "$FIFO"
