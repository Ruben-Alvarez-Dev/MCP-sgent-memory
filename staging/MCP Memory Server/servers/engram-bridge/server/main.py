"""Engram Bridge — Semantic Decision Memory (L3).

Engram stores curated decisions, entities, and patterns in Markdown files.
This bridge exposes them as MCP tools for the unified retrieval router.

Engram is filesystem-based (no Qdrant needed).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

mcp = FastMCP("engram-bridge")

# ── Configuration ──────────────────────────────────────────────────

ENGRAM_PATH = os.path.expanduser(os.getenv(
    "ENGRAM_PATH",
    str(Path.home() / ".memory" / "engram"),
)


def _ensure_engram_path():
    Path(ENGRAM_PATH).mkdir(parents=True, exist_ok=True)


def _get_engram_files() -> list[Path]:
    path = Path(ENGRAM_PATH)
    if not path.exists():
        return []
    return sorted(path.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def _read_engram_file(filepath: Path) -> dict[str, Any]:
    content = filepath.read_text()
    stat = filepath.stat()

    # Parse frontmatter if exists
    metadata = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    metadata[key.strip()] = val.strip()

    return {
        "file": str(filepath.relative_to(Path(ENGRAM_PATH))),
        "metadata": metadata,
        "content": body,
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "size": stat.st_size,
    }


# ── Public MCP Tools ──────────────────────────────────────────────


@mcp.tool()
async def save_decision(
    title: str,
    content: str,
    category: str = "decision",
    tags: str = "",
    scope: str = "agent",
) -> str:
    """Save a decision/entity/pattern to Engram.

    Args:
        title: Title of the memory.
        content: Full content (Markdown).
        category: decision | entity | pattern | config | preference
        tags: Comma-separated tags.
        scope: agent | domain | personal | global-core
    """
    _ensure_engram_path()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    filename = f"{title.lower().replace(' ', '-')}.md"

    filepath = Path(ENGRAM_PATH) / scope / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = f"---\ntitle: {title}\ncategory: {category}\ntags: {tag_list}\nscope: {scope}\ncreated: {datetime.utcnow().isoformat()}\n---\n\n"

    filepath.write_text(frontmatter + content)

    return json.dumps({
        "status": "saved",
        "file": str(filepath.relative_to(Path(ENGRAM_PATH))),
        "category": category,
        "scope": scope,
    }, indent=2)


@mcp.tool()
async def search_decisions(query: str, category: str = "", limit: int = 10) -> str:
    """Search Engram memories by keyword.

    Args:
        query: Search terms.
        category: Filter by category (decision | entity | pattern | config | preference).
        limit: Max results.
    """
    files = _get_engram_files()
    if not files:
        return json.dumps({"results": [], "message": "Engram store is empty"}, indent=2)

    query_terms = query.lower().split()
    results = []

    for f in files:
        try:
            data = _read_engram_file(f)
            searchable = f"{data['metadata'].get('title', '')} {data['content']}".lower()

            # Keyword matching
            matches = sum(1 for term in query_terms if term in searchable)
            if matches == 0:
                continue

            score = matches / len(query_terms)

            if category and data["metadata"].get("category", "") != category:
                continue

            results.append({
                "score": round(score, 4),
                "title": data["metadata"].get("title", f.name),
                "category": data["metadata"].get("category", "unknown"),
                "scope": data["metadata"].get("scope", "unknown"),
                "tags": data["metadata"].get("tags", []),
                "preview": data["content"][:300],
                "file": data["file"],
                "modified": data["modified_at"],
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return json.dumps({"query": query, "results": results[:limit]}, indent=2)


@mcp.tool()
async def get_decision(file_path: str) -> str:
    """Get a specific Engram memory by file path."""
    filepath = Path(ENGRAM_PATH) / file_path
    if not filepath.exists():
        return json.dumps({"error": f"File not found: {file_path}"}, indent=2)

    data = _read_engram_file(filepath)
    return json.dumps(data, indent=2)


@mcp.tool()
async def list_decisions(category: str = "", scope: str = "", limit: int = 20) -> str:
    """List Engram memories."""
    files = _get_engram_files()
    results = []

    for f in files:
        try:
            data = _read_engram_file(f)
            cat = data["metadata"].get("category", "")
            scp = data["metadata"].get("scope", "")

            if category and cat != category:
                continue
            if scope and scp != scope:
                continue

            results.append({
                "title": data["metadata"].get("title", f.name),
                "category": cat,
                "scope": scp,
                "tags": data["metadata"].get("tags", []),
                "modified": data["modified_at"],
                "file": data["file"],
            })
        except Exception:
            continue

        if len(results) >= limit:
            break

    return json.dumps({"count": len(results), "results": results}, indent=2)


@mcp.tool()
async def delete_decision(file_path: str) -> str:
    """Delete an Engram memory."""
    filepath = Path(ENGRAM_PATH) / file_path
    if not filepath.exists():
        return json.dumps({"error": f"File not found: {file_path}"}, indent=2)

    filepath.unlink()
    return json.dumps({"status": "deleted", "file": file_path}, indent=2)


@mcp.tool()
async def status() -> str:
    """Show Engram bridge status."""
    path = Path(ENGRAM_PATH)
    files = list(path.rglob("*.md")) if path.exists() else []

    return json.dumps({
        "daemon": "engram-bridge",
        "status": "RUNNING",
        "path": str(path),
        "exists": path.exists(),
        "total_memories": len(files),
        "scopes": list({f.parent.name for f in files}) if files else [],
    }, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
