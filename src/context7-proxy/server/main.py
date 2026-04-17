"""Context7 Proxy — Transparent proxy to context7 MCP API.

gentle-ai expects context7 tools (resolve-library-id, query-docs).
This proxy forwards those calls to the remote context7 API at
https://mcp.context7.com/mcp and returns the results unchanged.

The config key in opencode.json stays "context7" so tool names remain
"context7_resolve-library-id" etc — identical to what gentle-ai's prompts expect.

Future enhancement: cache results in Qdrant for repeated lookups.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("context7-proxy")

# ── Configuration ──────────────────────────────────────────────────

CONTEXT7_BASE_URL = os.getenv("CONTEXT7_BASE_URL", "https://mcp.context7.com/mcp")
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("CONTEXT7_TIMEOUT", "30"))


# ── HTTP helpers ───────────────────────────────────────────────────


async def _call_context7(method: str, params: dict) -> dict:
    """Call the context7 remote MCP server via HTTP."""
    headers = {"Content-Type": "application/json"}
    if CONTEXT7_API_KEY:
        headers["Authorization"] = f"Bearer {CONTEXT7_API_KEY}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(CONTEXT7_BASE_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            return {"error": data["error"].get("message", str(data["error"]))}

        return data.get("result", {})


async def _call_context7_tool(tool_name: str, arguments: dict) -> dict:
    """Call a specific tool on the context7 remote MCP server."""
    headers = {"Content-Type": "application/json"}
    if CONTEXT7_API_KEY:
        headers["Authorization"] = f"Bearer {CONTEXT7_API_KEY}"

    # MCP protocol: tools/call
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(CONTEXT7_BASE_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            return {"error": data["error"].get("message", str(data["error"]))}

        result = data.get("result", {})
        # MCP returns content as array of text blocks
        if "content" in result and isinstance(result["content"], list):
            texts = []
            for block in result["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return {"text": "\n".join(texts)}

        return result


# ── Public MCP Tools (context7-compatible interface) ──────────────


@mcp.tool()
async def resolve_library_id(
    query: str,
    libraryName: str = "",
) -> str:
    """Resolve a package/product name to a Context7-compatible library ID.

    Each result includes library ID, name, description, code snippets count,
    source reputation, and benchmark score.

    Args:
        query: The question or task you need help with.
        libraryName: The library name to search for.
    """
    try:
        result = await _call_context7_tool(
            "resolve-library-id",
            {
                "query": query,
                "libraryName": libraryName,
            },
        )

        text = result.get("text", "")
        if not text and "error" in result:
            return json.dumps({"error": result["error"]}, indent=2)

        return text if isinstance(text, str) else json.dumps(result, indent=2)

    except httpx.HTTPError as e:
        return json.dumps(
            {
                "error": f"context7 API unreachable: {e}",
                "fallback": "Check internet connection or context7.com status",
            },
            indent=2,
        )


@mcp.tool()
async def query_docs(
    libraryId: str,
    query: str,
) -> str:
    """Retrieve and query up-to-date documentation from Context7.

    You must call resolve-library-id first to obtain the exact library ID.

    Args:
        libraryId: Exact Context7-compatible library ID (e.g. '/mongodb/docs').
        query: The question or task. Be specific for best results.
    """
    try:
        result = await _call_context7_tool(
            "query-docs",
            {
                "libraryId": libraryId,
                "query": query,
            },
        )

        text = result.get("text", "")
        if not text and "error" in result:
            return json.dumps({"error": result["error"]}, indent=2)

        return text if isinstance(text, str) else json.dumps(result, indent=2)

    except httpx.HTTPError as e:
        return json.dumps(
            {
                "error": f"context7 API unreachable: {e}",
                "fallback": "Check internet connection or context7.com status",
            },
            indent=2,
        )


@mcp.tool()
async def status() -> str:
    """Show context7-proxy status."""
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(CONTEXT7_BASE_URL.replace("/mcp", "/"))
            reachable = resp.status_code < 500
    except Exception:
        pass

    return json.dumps(
        {
            "daemon": "context7-proxy",
            "status": "RUNNING",
            "upstream": CONTEXT7_BASE_URL,
            "upstream_reachable": reachable,
            "note": "Transparent proxy: gentle-ai calls → context7 API",
        },
        indent=2,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
