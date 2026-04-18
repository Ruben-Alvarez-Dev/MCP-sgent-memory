"""Repository indexing script for L2 hierarchical context retrieval."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import httpx
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from shared.embedding import EMBEDDING_DIM, bm25_tokenize, get_embedding
from shared.models.repo import RepoNode
from shared.retrieval.repo_map import _generic_file_node, _python_file_node
from shared.retrieval.code_map import generate_code_map, format_map_text


QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
SUPPORTED_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".go", ".rs", ".java", ".kt", ".c", ".h", ".cpp", ".hpp",
    ".rb", ".php", ".swift", ".zig",
    ".yaml", ".yml", ".toml", ".md", ".sh",
}


def _iter_repo_files(project_root: str) -> list[Path]:
    root = Path(project_root).resolve()
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in SUPPORTED_SUFFIXES and ".git" not in path.parts and "__pycache__" not in path.parts
    )


def _build_file_node(path: Path, root: Path) -> RepoNode:
    return _python_file_node(path, root) if path.suffix == ".py" else _generic_file_node(path, root)


def _node_content(node: RepoNode) -> str:
    deps = ", ".join(node.dependencies) if node.dependencies else "none"
    child_signatures = ", ".join(child.signature for child in node.children[:12]) if node.children else "none"
    return f"path: {node.path}\ntype: {node.type}\nsignature: {node.signature}\ndependencies: {deps}\nchildren: {child_signatures}"


def _point_id(node: RepoNode) -> str:
    raw = f"{node.path}:{node.type}:{node.signature}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _node_payload(node: RepoNode) -> dict:
    content = _node_content(node)
    return {
        "memory_id": _point_id(node),
        "layer": 2,
        "type": "repo_symbol",
        "node_type": node.type,
        "path": node.path,
        "signature": node.signature,
        "dependencies": node.dependencies,
        "content": content,
        "confidence": 0.85,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "repo_indexer",
    }


def build_repo_index_points(
    project_root: str,
    *,
    embed_fn: Callable[[str], list[float]] = get_embedding,
) -> list[dict]:
    root = Path(project_root).resolve()
    points: list[dict] = []

    for file_path in _iter_repo_files(project_root):
        file_node = _build_file_node(file_path, root)
        nodes = [file_node, *file_node.children]
        for node in nodes:
            payload = _node_payload(node)
            points.append(
                {
                    "id": payload["memory_id"],
                    "vector": embed_fn(payload["content"]),
                    "sparse_vectors": {"text": bm25_tokenize(payload["content"])},
                    "payload": payload,
                }
            )

    return points


async def _ensure_collection(client: httpx.AsyncClient, qdrant_url: str, collection: str) -> None:
    resp = await client.get(f"{qdrant_url}/collections")
    existing = [c["name"] for c in resp.json().get("result", {}).get("collections", [])]
    if collection in existing:
        return

    await client.put(
        f"{qdrant_url}/collections/{collection}",
        json={
            "vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
            "sparse_vectors": {"text": {"index": {"type": "bm25"}}},
        },
    )


async def upsert_repository_index(
    project_root: str,
    *,
    qdrant_url: str = QDRANT_URL,
    collection: str = QDRANT_COLLECTION,
    client: httpx.AsyncClient | None = None,
    embed_fn: Callable[[str], list[float]] = get_embedding,
) -> dict:
    points = build_repo_index_points(project_root, embed_fn=embed_fn)
    owns_client = client is None
    client = client or httpx.AsyncClient()

    try:
        await _ensure_collection(client, qdrant_url, collection)
        await client.put(
            f"{qdrant_url}/collections/{collection}/points?wait=true",
            json={"points": points},
        )
    finally:
        if owns_client:
            await client.aclose()

    return {
        "indexed_points": len(points),
        "collection": collection,
        "project_root": str(Path(project_root).resolve()),
    }


# ── Code Map Indexing (SPEC-1.2) ──────────────────────────────────

def build_code_map_points(
    project_root: str,
    *,
    embed_fn: Callable[[str], list[float]] = get_embedding,
    exclude: set[str] | None = None,
) -> list[dict]:
    """Build Qdrant points from code maps for all source files.

    Uses the new code_map.py generator for 30+ languages.
    Stores as type='code_map' in L2 alongside existing 'repo_symbol' points.
    """
    if exclude is None:
        exclude = {".git", "node_modules", "__pycache__", ".venv", "qdrant",
                   "dist", "build", "target", "vendor",
                   "llama.cpp", ".cache", ".tox", ".mypy_cache", ".pytest_cache"}

    root = Path(project_root).resolve()
    points: list[dict] = []

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        # Check exclude dirs
        parts = set(file_path.relative_to(root).parts)
        if parts & exclude:
            continue

        code_map = generate_code_map(str(file_path), project_root)
        if code_map is None:
            continue

        content = code_map.map_text
        if not content.strip():
            continue

        point_id = hashlib.sha256(
            f"code_map:{code_map.file_path}:{code_map.sha}".encode()
        ).hexdigest()[:16]

        payload = {
            "memory_id": point_id,
            "layer": 2,
            "type": "code_map",
            "file_path": code_map.file_path,
            "sha": code_map.sha,
            "language": code_map.language,
            "lines_total": code_map.lines_total,
            "chars_total": code_map.chars_total,
            "symbol_count": len(code_map.symbols),
            "imports": code_map.imports,
            "exports": code_map.exports,
            "content": content,
            "summary": code_map.summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "code_map_indexer",
        }

        points.append({
            "id": point_id,
            "vector": embed_fn(content),
            "sparse_vectors": {"text": bm25_tokenize(content)},
            "payload": payload,
        })

    return points


async def upsert_code_map_index(
    project_root: str,
    *,
    qdrant_url: str = QDRANT_URL,
    collection: str = QDRANT_COLLECTION,
    client: httpx.AsyncClient | None = None,
    embed_fn: Callable[[str], list[float]] = get_embedding,
) -> dict:
    """Index code maps into Qdrant L2.

    Generates maps for all source files and upserts as type='code_map'.
    """
    points = build_code_map_points(project_root, embed_fn=embed_fn)
    owns_client = client is None
    client = client or httpx.AsyncClient()

    try:
        await _ensure_collection(client, qdrant_url, collection)
        if points:
            await client.put(
                f"{qdrant_url}/collections/{collection}/points?wait=true",
                json={"points": points},
            )
    finally:
        if owns_client:
            await client.aclose()

    return {
        "indexed_maps": len(points),
        "collection": collection,
        "project_root": str(Path(project_root).resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a repository into Qdrant L2 repo symbols.")
    parser.add_argument("project_root", nargs="?", default=".", help="Repository root to index")
    parser.add_argument("--qdrant-url", default=QDRANT_URL, help="Qdrant base URL")
    parser.add_argument("--collection", default=QDRANT_COLLECTION, help="Target Qdrant collection")
    args = parser.parse_args()

    result = asyncio.run(
        upsert_repository_index(
            args.project_root,
            qdrant_url=args.qdrant_url,
            collection=args.collection,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
