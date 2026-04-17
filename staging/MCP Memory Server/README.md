# MCP Memory Server

Self-contained memory system with bundled llama.cpp engine.
No Docker. No Homebrew. No external dependencies.

## Install

Double-click `install.sh` or run:
```bash
./install.sh
```

Default: `~/MCP-servers/MCP-memory-server/`

## What's included

- **engine/** — llama.cpp binary + bundled libraries
- **models/** — all-MiniLM-L6-v2 embedding model
- **servers/** — 7 MCP servers
- **shared/** — Data models and embedding wrapper

## After install

```bash
source ~/MCP-servers/MCP-memory-server/.venv/bin/activate
cd ~/MCP-servers/MCP-memory-server/servers/automem/server
python3 main.py
```
