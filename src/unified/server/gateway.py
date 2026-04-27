"""MCP Gateway Proxy — HTTP to stdio bridge (Fase 3B).

Receives MCP requests via HTTP and forwards them to the unified server
running on stdio. Useful when the MCP client only supports HTTP but
the server runs on stdio.

Architecture:
    MCP Client → HTTP :8080 → Gateway Proxy → stdio → Unified Server

Usage:
    python -m unified.server.gateway --port 8080

This is a lightweight alternative to Fase 3C (streamable-http).
The gateway spawns the unified server as a subprocess and communicates
via stdio, while exposing an HTTP interface to clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))


async def handle_request(request_body: dict, server_process) -> dict:
    """Forward a JSON-RPC request to the stdio server and return the response."""
    request_json = json.dumps(request_body) + "\n"
    server_process.stdin.write(request_json.encode())
    await server_process.stdin.drain()

    response_line = await server_process.stdout.readline()
    if not response_line:
        return {"error": {"code": -32603, "message": "Server closed connection"}}
    return json.loads(response_line)


async def start_gateway(port: int = 8080):
    """Start the HTTP gateway proxy."""
    try:
        from aiohttp import web
    except ImportError:
        logger.error("aiohttp required for gateway: pip install aiohttp")
        sys.exit(1)

    # Spawn the unified server as a subprocess
    server_script = str(BASE_DIR / "unified" / "server" / "main.py")
    process = await asyncio.create_subprocess_exec(
        sys.executable, server_script,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    logger.info("Unified server spawned (PID %d)", process.pid)

    async def handle_post(request):
        """Handle incoming MCP JSON-RPC requests."""
        try:
            body = await request.json()
            response = await handle_request(body, process)
            return web.json_response(response)
        except Exception as e:
            return web.json_response(
                {"error": {"code": -32603, "message": str(e)}},
                status=500,
            )

    async def handle_health(request):
        """Health check endpoint."""
        return web.json_response({"status": "ok", "transport": "gateway"})

    app = web.Application()
    app.router.add_post("/", handle_post)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Gateway listening on http://0.0.0.0:%d", port)

    # Keep running
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        process.terminate()
        await process.wait()
        await runner.cleanup()


def main():
    port = int(os.environ.get("GATEWAY_PORT", "8080"))
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_gateway(port))


if __name__ == "__main__":
    main()
