"""Engram Facade — Transparent bridge between gentle-ai and memory-server.

gentle-ai expects engram standalone tools (mem_save, mem_search, etc).
This facade accepts those EXACT calls and routes them through the
memory-server 6-layer pipeline:

  mem_save       → automem.memorize (L0+L1) + engram-bridge.save_decision (L3)
  mem_search     → vk-cache retrieval router (L1-L4, dense+BM25+RRF)
  mem_get_observation → engram-bridge filesystem read (L3)
  mem_update     → engram-bridge filesystem upsert (L3)
  mem_context    → vk-cache.request_context (L5 context pack)
  mem_session_*  → automem + conversation-store + autodream
  mem_suggest_topic_key → deterministic key normalization

The config key in opencode.json stays "engram" so tool names remain
"engram_mem_save" etc — identical to what gentle-ai's prompts expect.

Uses shared modules directly from the memory-server codebase.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Bootstrap: find the MEMORY_SERVER_DIR and add to path ─────────
# This MUST happen before any project imports.
# Walk up from this script until we find shared/__init__.py
_script_dir = Path(__file__).resolve().parent
_project_root = None
_candidate = _script_dir
for _ in range(5):
    _candidate = _candidate.parent
    if (_candidate / "shared" / "__init__.py").exists():
        _project_root = _candidate
        break

if _project_root is None:
    # Fallback: use MEMORY_SERVER_DIR env var if set
    _env_dir = os.getenv("MEMORY_SERVER_DIR", "")
    if _env_dir and Path(_env_dir).exists():
        _project_root = Path(_env_dir)

if _project_root and str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Now we can import project modules
from shared.env_loader import load_env

_env_path = load_env()

import httpx
from mcp.server.fastmcp import FastMCP
from shared.models import MemoryItem, MemoryLayer, MemoryScope, MemoryType

mcp = FastMCP("engram-facade")

# ── Configuration (all from central .env via env_loader) ──────────

ENGRAM_PATH = os.path.expanduser(
    os.getenv("ENGRAM_PATH", str(Path.home() / ".memory" / "engram"))
)
GATEWAY_URL = os.getenv("MEMORY_SERVER_URL", "http://127.0.0.1:3050")

# Direct mode uses shared modules (faster), gateway mode uses HTTP
DIRECT_MODE = os.getenv("ENGRAM_FACADE_MODE", "direct").lower() == "direct"

if DIRECT_MODE:
    from shared.embedding import get_embedding as llama_embed, bm25_tokenize
    from shared.vault_manager import vault as _vault

    QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

    import asyncio

    async def _embed(text: str) -> list[float]:
        from shared.embedding import _ensure_binaries

        _ensure_binaries()
        return await asyncio.to_thread(llama_embed, text)

    async def _store_in_qdrant(
        content: str, scope: str, scope_id: str, mem_type: str, tags: list[str]
    ):
        """Store directly in Qdrant L1 working memory."""
        vector = await _embed(content)
        sparse = bm25_tokenize(content)
        item = MemoryItem(
            layer=MemoryLayer.WORKING,
            scope_type=MemoryScope.SESSION if scope == "session" else MemoryScope.AGENT,
            scope_id=scope_id,
            type=MemoryType(mem_type),
            content=content,
            importance=0.5,
            topic_ids=tags,
        )
        point = {
            "id": item.memory_id,
            "vector": vector,
            "sparse_vectors": {"text": sparse},
            "payload": item.model_dump(mode="json"),
        }
        async with httpx.AsyncClient() as client:
            # Ensure collection exists
            resp = await client.get(f"{QDRANT_URL}/collections")
            existing = [
                c["name"] for c in resp.json().get("result", {}).get("collections", [])
            ]
            if QDRANT_COLLECTION not in existing:
                await client.put(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
                    json={
                        "vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
                        "sparse_vectors": {"text": {"index": {"type": "bm25"}}},
                    },
                )
            await client.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
                json={"points": [point]},
            )
        return item.memory_id

    async def _append_raw_jsonl(content: str, source: str, actor_id: str):
        """Append raw event to JSONL (L0 audit trail)."""
        jsonl_path = Path.home() / ".memory" / "raw_events.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_id": str(uuid.uuid4()),
            "type": "agent_action",
            "source": source,
            "actor_id": actor_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": content[:2000],
        }
        with open(jsonl_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    async def _search_qdrant(
        query: str, limit: int = 10, project: str = ""
    ) -> list[dict]:
        """Search Qdrant for relevant memories across L1-L4."""
        vector = await _embed(query)
        filter_must = []
        if project:
            filter_must.append({"key": "scope_id", "match": {"value": project}})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
                json={
                    "vector": vector,
                    "limit": limit,
                    "score_threshold": 0.3,
                    "with_payload": True,
                    **({"filter": {"must": filter_must}} if filter_must else {}),
                },
            )
            if resp.status_code != 200:
                return []
            result_data = resp.json().get("result", [])
            points = (
                result_data
                if isinstance(result_data, list)
                else result_data.get("result", [])
            )
            return [
                {
                    "id": p["id"],
                    "score": p.get("score", 0),
                    "content": p.get("payload", {}).get("content", ""),
                    "title": p.get("payload", {}).get("topic_ids", [""])[0]
                    if p.get("payload", {}).get("topic_ids")
                    else "",
                    "type": p.get("payload", {}).get("type", ""),
                    "scope": p.get("payload", {}).get("scope_id", ""),
                    "created_at": p.get("payload", {}).get("created_at", ""),
                }
                for p in points
            ]


# ── Engram filesystem helpers (same format as engram-bridge) ──────


def _ensure_engram_path():
    Path(ENGRAM_PATH).mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    """Normalize text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80]


def _write_engram_file(
    title: str,
    content: str,
    type_: str,
    project: str,
    scope: str,
    topic_key: str,
    tags: list[str],
) -> str:
    """Write an engram-compatible markdown file with frontmatter."""
    _ensure_engram_path()

    # Determine path: use topic_key for stable file naming
    if topic_key:
        filename = f"{_slugify(topic_key)}.md"
    else:
        filename = f"{_slugify(title)}.md"

    filepath = Path(ENGRAM_PATH) / scope / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Build frontmatter (compatible with engram-bridge format)
    import yaml

    try:
        frontmatter = yaml.safe_dump(
            {
                "title": title,
                "type": type_,
                "project": project,
                "scope": scope,
                "topic_key": topic_key,
                "tags": tags,
                "created": datetime.utcnow().isoformat(),
            },
            default_flow_style=False,
        ).strip()
    except ImportError:
        # Fallback without yaml
        frontmatter = "\n".join(
            f"{k}: {v}"
            for k, v in {
                "title": title,
                "type": type_,
                "project": project,
                "scope": scope,
                "topic_key": topic_key,
                "tags": tags,
                "created": datetime.utcnow().isoformat(),
            }.items()
        )

    full_content = f"---\n{frontmatter}\n---\n\n{content}"
    filepath.write_text(full_content, encoding="utf-8")

    return str(filepath.relative_to(Path(ENGRAM_PATH)))


def _read_engram_file(filepath: Path) -> dict[str, Any]:
    """Read an engram markdown file with frontmatter."""
    content = filepath.read_text(encoding="utf-8")
    stat = filepath.stat()

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
                    val = val.strip().strip('"').strip("'")
                    if val.startswith("["):
                        try:
                            val = json.loads(val.replace("'", '"'))
                        except Exception:
                            pass
                    metadata[key.strip()] = val

    return {
        "id": str(filepath.relative_to(Path(ENGRAM_PATH))),
        "title": metadata.get("title", filepath.stem),
        "type": metadata.get("type", "manual"),
        "project": metadata.get("project", ""),
        "scope": metadata.get("scope", "project"),
        "topic_key": metadata.get("topic_key", ""),
        "tags": metadata.get("tags", []),
        "content": body,
        "created_at": metadata.get("created", ""),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def _search_engram_fs(query: str, project: str = "", limit: int = 10) -> list[dict]:
    """Search engram filesystem by keywords (same as engram-bridge)."""
    path = Path(ENGRAM_PATH)
    if not path.exists():
        return []

    query_terms = query.lower().split()
    results = []

    for f in path.rglob("*.md"):
        try:
            data = _read_engram_file(f)
            searchable = f"{data.get('title', '')} {data.get('content', '')} {data.get('topic_key', '')}".lower()

            matches = sum(1 for term in query_terms if term in searchable)
            if matches == 0:
                continue

            if project and data.get("project", "") != project:
                continue

            results.append(
                {
                    "id": data["id"],
                    "title": data.get("title", ""),
                    "score": round(matches / len(query_terms), 4),
                    "content": data.get("content", "")[:300],
                    "type": data.get("type", ""),
                    "scope": data.get("scope", ""),
                    "project": data.get("project", ""),
                }
            )
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ── Public MCP Tools (engram-compatible interface) ────────────────


@mcp.tool()
async def mem_save(
    title: str,
    content: str,
    type: str = "manual",
    project: str = "",
    scope: str = "project",
    topic_key: str = "",
    tags: str = "",
    session_id: str = "",
) -> str:
    """Save an important observation to persistent memory.

    Args:
        title: Short, searchable title (e.g. 'JWT auth middleware')
        content: Structured content using What/Why/Where/Learned format
        type: Category: decision, architecture, bugfix, pattern, config, discovery, learning, manual
        project: Project name
        scope: 'project' (default) or 'personal'
        topic_key: Optional stable key for upserts (e.g. 'architecture/auth-model')
        tags: Comma-separated tags
        session_id: Session ID to associate with
    """
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    # 1. Write to L3 filesystem (engram-bridge compatible format)
    file_path = _write_engram_file(
        title=title,
        content=content,
        type_=type,
        project=project,
        scope=scope,
        topic_key=topic_key,
        tags=tags_list,
    )

    result_parts = [f"Memory saved. Title: {title}", f"File: {file_path}"]

    # 2. Also store in L0+L1 (pipeline upgrade) if direct mode
    if DIRECT_MODE:
        try:
            # L0 audit trail
            await _append_raw_jsonl(
                content,
                source="engram-facade",
                actor_id=session_id or project or "manual",
            )
            # L1 working memory in Qdrant
            mem_id = await _store_in_qdrant(
                content=content,
                scope=scope,
                scope_id=project or "default",
                mem_type=type,
                tags=tags_list,
            )
            result_parts.append(f"L0+L1 pipeline: stored (id: {mem_id[:8]}...)")
        except Exception as e:
            result_parts.append(f"L0+L1 pipeline: skipped ({e})")

    return "\n".join(result_parts)


@mcp.tool()
async def mem_search(
    query: str,
    project: str = "",
    limit: int = 10,
    scope: str = "",
    type: str = "",
) -> str:
    """Search persistent memory across all layers.

    Returns observations with ID, title, type, and preview content.

    Args:
        query: Natural language or keywords
        project: Filter by project name
        limit: Max results (default 10, max 20)
        scope: Filter by scope: project or personal
        type: Filter by type: decision, architecture, bugfix, pattern, etc.
    """
    limit = min(limit, 20)
    all_results = []

    # 1. Search L3 filesystem (engram-bridge compatible)
    fs_results = _search_engram_fs(query, project=project, limit=limit)
    for r in fs_results:
        r["source"] = "L3-filesystem"
        all_results.append(r)

    # 2. Search L1-L4 Qdrant (pipeline upgrade) if direct mode
    if DIRECT_MODE:
        try:
            qdrant_results = await _search_qdrant(query, limit=limit, project=project)
            for r in qdrant_results:
                r["source"] = "L1-L4-qdrant"
                all_results.append(r)
        except Exception:
            pass  # Qdrant unavailable, filesystem results suffice

    # Deduplicate by content similarity
    seen_hashes = set()
    unique = []
    for r in all_results:
        h = hashlib.md5(r.get("content", "")[:100].encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(r)

    # Sort by score descending
    unique.sort(key=lambda x: x.get("score", 0), reverse=True)

    observations = []
    for r in unique[:limit]:
        observations.append(
            {
                "id": r.get("id", ""),
                "title": r.get("title", ""),
                "type": r.get("type", ""),
                "scope": r.get("scope", ""),
                "project": r.get("project", ""),
                "source": r.get("source", ""),
                "content": r.get("content", "")[:300],  # Truncated preview
            }
        )

    # Suggest topic_key if found
    suggested = ""
    if unique:
        top = unique[0]
        suggested = top.get("topic_key", "") or _slugify(top.get("title", ""))

    return json.dumps(
        {
            "observations": observations,
            "total": len(observations),
            "suggested_topic_key": suggested,
        },
        indent=2,
    )


@mcp.tool()
async def mem_get_observation(id: str) -> str:
    """Get the full, untruncated content of a specific observation by ID.

    ALWAYS call this after mem_search to get complete content.
    Search results are truncated to 300 chars — this returns everything.

    Args:
        id: The observation ID (file path relative to engram store)
    """
    filepath = Path(ENGRAM_PATH) / id
    if not filepath.exists():
        return json.dumps({"error": f"Observation not found: {id}"}, indent=2)

    data = _read_engram_file(filepath)
    return json.dumps(data, indent=2)


@mcp.tool()
async def mem_update(
    id: str,
    title: str = "",
    content: str = "",
    type: str = "",
    project: str = "",
    scope: str = "",
    topic_key: str = "",
) -> str:
    """Update an existing observation by ID. Only provided fields are changed.

    Args:
        id: The observation ID to update
        title: New title (optional)
        content: New content (optional)
        type: New type/category (optional)
        project: New project value (optional)
        scope: New scope (optional)
        topic_key: New topic key (optional)
    """
    filepath = Path(ENGRAM_PATH) / id
    if not filepath.exists():
        return json.dumps({"error": f"Observation not found: {id}"}, indent=2)

    existing = _read_engram_file(filepath)

    # Merge: use provided values, fall back to existing
    new_title = title or existing.get("title", "")
    new_content = content or existing.get("content", "")
    new_type = type or existing.get("type", "manual")
    new_project = project or existing.get("project", "")
    new_scope = scope or existing.get("scope", "project")
    new_topic_key = topic_key or existing.get("topic_key", "")
    new_tags = existing.get("tags", [])

    file_path = _write_engram_file(
        title=new_title,
        content=new_content,
        type_=new_type,
        project=new_project,
        scope=new_scope,
        topic_key=new_topic_key,
        tags=new_tags if isinstance(new_tags, list) else [new_tags],
    )

    return json.dumps({"status": "updated", "id": id, "file": file_path}, indent=2)


@mcp.tool()
async def mem_context(
    limit: int = 20,
    project: str = "",
    scope: str = "",
) -> str:
    """Get recent memory context from previous sessions.

    Shows recent sessions and observations to understand what was done before.

    Args:
        limit: Number of observations to retrieve (default 20)
        project: Filter by project name
        scope: Filter by scope: project (default) or personal
    """
    path = Path(ENGRAM_PATH)
    if not path.exists():
        return json.dumps(
            {"observations": [], "message": "No memories stored yet"}, indent=2
        )

    observations = []
    files = sorted(path.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    for f in files[:limit]:
        try:
            data = _read_engram_file(f)
            if project and data.get("project", "") != project:
                continue
            if scope and data.get("scope", "") != scope:
                continue
            observations.append(
                {
                    "id": data["id"],
                    "title": data.get("title", ""),
                    "type": data.get("type", ""),
                    "scope": data.get("scope", ""),
                    "project": data.get("project", ""),
                    "created_at": data.get("created_at", ""),
                    "preview": data.get("content", "")[:200],
                }
            )
        except Exception:
            continue

    return json.dumps(
        {"observations": observations, "total": len(observations)}, indent=2
    )


@mcp.tool()
async def mem_save_prompt(
    content: str,
    project: str = "",
    session_id: str = "",
) -> str:
    """Save a user prompt to persistent memory for context tracking.

    Args:
        content: The user's prompt text
        project: Project name
        session_id: Session ID to associate with
    """
    _ensure_engram_path()
    filename = f"prompt-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}.md"
    filepath = Path(ENGRAM_PATH) / "project" / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = f"---\ntype: prompt\nproject: {project}\nsession: {session_id}\ncreated: {datetime.utcnow().isoformat()}\n---\n\n"
    filepath.write_text(frontmatter + content, encoding="utf-8")

    return json.dumps(
        {"status": "saved", "id": str(filepath.relative_to(Path(ENGRAM_PATH)))},
        indent=2,
    )


@mcp.tool()
async def mem_session_start(
    id: str,
    project: str,
    directory: str = "",
) -> str:
    """Register the start of a new coding session.

    Args:
        id: Unique session identifier
        project: Project name
        directory: Working directory
    """
    # Record session start in engram
    _ensure_engram_path()
    filepath = Path(ENGRAM_PATH) / "project" / f"session-{_slugify(id)}.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    content = f"Session started: {id}\nProject: {project}\nDirectory: {directory}\nStarted: {datetime.utcnow().isoformat()}"
    frontmatter = f"---\ntype: session\nproject: {project}\nsession_id: {id}\nstatus: active\ncreated: {datetime.utcnow().isoformat()}\n---\n\n"
    filepath.write_text(frontmatter + content, encoding="utf-8")

    # L0+L1 pipeline
    if DIRECT_MODE:
        try:
            await _append_raw_jsonl(
                f"Session started: {project}", source="engram-facade", actor_id=id
            )
        except Exception:
            pass

    return json.dumps(
        {"status": "started", "session_id": id, "project": project}, indent=2
    )


@mcp.tool()
async def mem_session_end(
    id: str,
    project: str = "",
    summary: str = "",
) -> str:
    """Mark a coding session as completed with optional summary.

    Args:
        id: Session identifier to close
        project: Project name
        summary: Summary of what was accomplished
    """
    # Update session file
    session_file = Path(ENGRAM_PATH) / "project" / f"session-{_slugify(id)}.md"
    if session_file.exists():
        data = _read_engram_file(session_file)
        existing_content = data.get("content", "")
        updated = existing_content + f"\n\nEnded: {datetime.utcnow().isoformat()}"
        if summary:
            updated += f"\n\nSummary:\n{summary}"
        frontmatter = f"---\ntype: session\nproject: {project}\nsession_id: {id}\nstatus: completed\ncreated: {data.get('created_at', '')}\nended: {datetime.utcnow().isoformat()}\n---\n\n"
        session_file.write_text(frontmatter + updated, encoding="utf-8")

    # L0 trail
    if DIRECT_MODE:
        try:
            await _append_raw_jsonl(
                f"Session ended: {id} ({project}). Summary: {summary[:500]}",
                source="engram-facade",
                actor_id=id,
            )
        except Exception:
            pass

    return json.dumps({"status": "ended", "session_id": id}, indent=2)


@mcp.tool()
async def mem_session_summary(
    content: str,
    project: str,
    session_id: str = "",
) -> str:
    """Save a comprehensive end-of-session summary.

    Args:
        content: Full session summary using Goal/Instructions/Discoveries/Accomplished/Files format
        project: Project name
        session_id: Session ID (default: manual-save-{project})
    """
    if not session_id:
        session_id = f"manual-save-{project}"

    # Save as decision (L3)
    file_path = _write_engram_file(
        title=f"Session summary: {project}",
        content=content,
        type_="summary",
        project=project,
        scope="project",
        topic_key=f"session/{project}/{datetime.utcnow().strftime('%Y%m%d')}",
        tags=["session-summary", project],
    )

    # L0+L1 pipeline
    if DIRECT_MODE:
        try:
            await _append_raw_jsonl(
                content[:1000], source="engram-facade", actor_id=session_id
            )
            await _store_in_qdrant(
                content=content,
                scope="project",
                scope_id=project,
                mem_type="summary",
                tags=["session-summary", project],
            )
        except Exception:
            pass

    return json.dumps({"status": "saved", "file": file_path}, indent=2)


@mcp.tool()
async def mem_suggest_topic_key(
    title: str = "",
    content: str = "",
    type: str = "",
) -> str:
    """Suggest a stable topic_key for memory upserts.

    Args:
        title: Observation title (preferred input for stable keys)
        content: Observation content used as fallback if title is empty
        type: Observation type/category, e.g. architecture, decision, bugfix
    """
    source = title or content or ""
    if not source:
        return json.dumps({"topic_key": "untitled"}, indent=2)

    # Normalize: lowercase, remove special chars, replace spaces with hyphens
    key = source.lower().strip()
    key = re.sub(r"[^a-z0-9\s-]", "", key)
    key = re.sub(r"\s+", "-", key)
    key = re.sub(r"-+", "-", key)
    key = key[:60].rstrip("-")

    # Prepend type prefix for organization
    if type:
        type_prefix = type.lower().replace("_", "-")
        if not key.startswith(type_prefix):
            key = f"{type_prefix}/{key}"

    return json.dumps({"topic_key": key}, indent=2)


@mcp.tool()
async def status() -> str:
    """Show engram-facade status."""
    path = Path(ENGRAM_PATH)
    files = list(path.rglob("*.md")) if path.exists() else []

    # Check pipeline status
    pipeline_status = "UNKNOWN"
    if DIRECT_MODE:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{QDRANT_URL}/collections", timeout=3)
                pipeline_status = "OK" if resp.status_code == 200 else "DOWN"
        except Exception:
            pipeline_status = "UNREACHABLE"

    return json.dumps(
        {
            "daemon": "engram-facade",
            "status": "RUNNING",
            "mode": "direct" if DIRECT_MODE else "gateway",
            "engram_path": str(path),
            "total_memories": len(files),
            "pipeline_l0_l1": pipeline_status,
            "note": "Transparent bridge: gentle-ai calls → 6-layer memory pipeline",
        },
        indent=2,
    )


# ── Passive capture tools (used by skills overlay) ────────────────


@mcp.tool()
async def mem_capture_passive(
    content: str,
    project: str = "",
    session_id: str = "",
    source: str = "subagent-stop",
) -> str:
    """Extract and save structured learnings from text output.

    Looks for '## Key Learnings:' or '## Aprendizajes Clave:' sections
    and extracts numbered or bulleted items as separate observations.

    Args:
        content: Text output containing a learnings section
        project: Project name
        session_id: Session ID
        source: Source identifier
    """
    import re

    # Extract learnings section
    patterns = [
        r"##\s*(?:Key Learnings|Aprendizajes Clave)\s*:?\s*\n(.*?)(?=\n##|\Z)",
        r"\*\*(?:Key Learnings|Aprendizajes Clave)\*\*\s*:?\s*\n(.*?)(?=\n\*\*|\Z)",
    ]

    learnings = []
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            for line in match.strip().split("\n"):
                line = line.strip()
                # Match numbered or bulleted items
                item = re.sub(r"^[-*]\s+", "", line)
                item = re.sub(r"^\d+\.\s+", "", item)
                if item and len(item) > 10:
                    learnings.append(item)

    if not learnings:
        return json.dumps(
            {"status": "no_learnings_found", "project": project}, indent=2
        )

    # Save each learning as a separate observation
    saved = []
    for i, learning in enumerate(learnings[:10]):
        file_path = _write_engram_file(
            title=f"Learning: {learning[:50]}...",
            content=learning,
            type_="learning",
            project=project,
            scope="project",
            topic_key=f"learning/{project}/{_slugify(learning[:40])}",
            tags=["passive-capture", "learning", project],
        )
        saved.append(file_path)

    return json.dumps(
        {
            "status": "captured",
            "learnings_found": len(learnings),
            "saved": len(saved),
            "files": saved,
        },
        indent=2,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
