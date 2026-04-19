from __future__ import annotations
import asyncio
import uuid
from pathlib import Path
from typing import Callable, List, Coroutine
import httpx
from shared.retrieval.code_map import generate_code_map, CodeMap

# Default values from FUSION-SPEC-v3.md
DEFAULT_SUFFIXES = [".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".yaml", ".md"]
DEFAULT_EXCLUDE = [".git", "node_modules", "__pycache__", ".venv", "qdrant_storage"]
BATCH_SIZE = 32

async def _build_code_map_points(
    project_root: str, 
    embed_fn: Callable[[str], Coroutine[None, None, List[float]]]
) -> List[dict]:
    """Generates Qdrant points for all code maps in a project."""
    root_path = Path(project_root)
    files_to_process = [
        f for f in root_path.rglob('*') 
        if f.is_file() and 
           f.suffix in DEFAULT_SUFFIXES and 
           not any(part in f.parts for part in DEFAULT_EXCLUDE)
    ]

    points = []
    for file_path in files_to_process:
        code_map = generate_code_map(str(file_path))
        if not code_map:
            continue

        embedding = await embed_fn(code_map.summary)
        
        # Payload must not contain None values for Qdrant
        payload = {
            "layer": 2,
            "type": "code_map",
            "file_path": code_map.file_path,
            "sha": code_map.sha,
            "language": code_map.language,
            "lines_total": code_map.lines_total,
            "symbol_count": len(code_map.symbols),
            "imports": code_map.imports,
            "exports": code_map.exports,
            "content": code_map.map_text,
            "map_text": code_map.map_text,
            "summary": code_map.summary,
            "created_at": code_map.created_at,
            "source": "code_map_indexer"
        }
        
        # Unique ID based on file path to ensure upserts replace existing docs
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"code_map:{code_map.file_path}"))

        points.append({
            "id": point_id,
            "vector": embedding,
            "payload": payload
        })
    return points


async def upsert_repository_index(
    project_root: str,
    qdrant_url: str,
    collection: str,
    client: httpx.AsyncClient,
    embed_fn: Callable[[str], Coroutine[None, None, List[float]]],
    *args,
    **kwargs
):
    """
    Generates code maps for all files in a repository and upserts them into Qdrant.
    This replaces the previous placeholder.
    """
    print("INFO: Starting code map generation and indexing...")
    points = await _build_code_map_points(project_root, embed_fn)
    
    if not points:
        print("INFO: No new code maps to index.")
        return

    # Upsert points to Qdrant in batches
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        url = f"{qdrant_url}/collections/{collection}/points"
        
        try:
            response = await client.put(
                url,
                json={"points": batch},
                params={"wait": "true"}, # wait for the operation to complete
                timeout=60.0
            )
            response.raise_for_status()
            print(f"INFO: Successfully upserted batch {i//BATCH_SIZE + 1}/{(len(points) + BATCH_SIZE - 1)//BATCH_SIZE}.")
        except httpx.HTTPStatusError as e:
            print(f"ERROR: Failed to upsert batch to Qdrant. Status: {e.response.status_code}, Response: {e.response.text}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during Qdrant upsert: {e}")

    print(f"INFO: Finished indexing. Upserted {len(points)} code maps.")
    return
