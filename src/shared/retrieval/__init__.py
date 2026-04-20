from dataclasses import dataclass
import os
from typing import List, Dict
import asyncio
import httpx
from pydantic import BaseModel
from .index_repo import upsert_repository_index
from shared.llm.config import rank_by_relevance, ContextItem, QueryIntent
from shared.models.repo import RepoNode
from shared.embedding import get_embedding as _real_get_embedding, get_embedding_spec


def get_repo_map(file_path: str, project_root: str = "") -> str:
    """Retrieve a tree representation of the repository structure."""
    from pathlib import Path
    root = Path(project_root) if project_root else Path(file_path).parent
    lines = []
    for p in sorted(root.rglob("*")):
        if any(part in p.parts for part in {".git", "node_modules", "__pycache__", ".venv", "qdrant_storage"}):
            continue
        rel = p.relative_to(root)
        prefix = "  " * (len(rel.parts) - 1) if len(rel.parts) > 1 else ""
        marker = "/" if p.is_dir() else ""
        lines.append(f"{prefix}{rel.name}{marker}")
    return "\n".join(lines) if lines else f"{file_path}"


def prune_content(source: str, path: str = "", max_tokens: int = 100) -> str:
    """Prune content to fit within token limits while preserving structure."""
    import ast
    if not source or max_tokens <= 0:
        return ""
    # Rough token estimate: 1 token ≈ 4 chars
    max_chars = max_tokens * 4
    if len(source) <= max_chars:
        return source
    # For Python, try AST-aware pruning
    if path.endswith(".py"):
        try:
            tree = ast.parse(source)
            pruned_parts = []
            current_len = 0
            for node in ast.iter_child_nodes(tree):
                segment = ast.get_source_segment(source, node)
                if segment and current_len + len(segment) <= max_chars:
                    pruned_parts.append(segment)
                    current_len += len(segment)
                elif segment:
                    # Include just the signature/first line
                    first_line = segment.split("\n")[0]
                    pruned_parts.append(first_line + " ...")
                    current_len += len(first_line) + 4
            return "\n".join(pruned_parts)
        except SyntaxError:
            pass
    # Generic truncation at last complete line
    truncated = source[:max_chars]
    last_newline = truncated.rfind("\n")
    return truncated[:last_newline] if last_newline > 0 else truncated

@dataclass
class ContextPack:
    query: str
    total_tokens: int
    sections: List[Dict[str, str]]

def get_embedding(text: str) -> list[float]:
    """Get embedding vector using the shared embedding backend."""
    return _real_get_embedding(text)

def classify_intent(query: str) -> QueryIntent:
    """Classify query intent using heuristic keyword analysis.

    Determines the type of query to optimize retrieval strategy:
    - code_lookup: Searching for specific code, functions, or files.
    - plan: Planning or architecture questions.
    - debug: Error diagnosis or debugging questions.
    - answer: General knowledge or conceptual questions.
    """
    q = query.lower()

    # Extract potential entity names (CamelCase, snake_case identifiers)
    import re
    entities = re.findall(r'[A-Z][a-zA-Z]+|_[a-z]+_|`[^`]+`', query)

    # Determine intent type from keywords (order matters: more specific first)
    if any(kw in q for kw in ("error", "bug", "fix", "debug", "crash", "traceback", "exception", "fail")):
        intent_type = "debug"
    elif any(kw in q for kw in ("where is", "find", "locate", "file", "function", "class", "method", "import")):
        intent_type = "code_lookup"
    elif any(kw in q for kw in ("plan", "design", "architect", "how should", "approach", "strategy")):
        intent_type = "plan"
    else:
        intent_type = "answer"

    # Determine scope
    if any(kw in q for kw in ("external", "docs", "documentation", "library", "package")):
        scope = "external"
    else:
        scope = "this_project"

    # Determine if external resources are needed
    needs_external = scope == "external" or any(
        kw in q for kw in ("latest", "current", "version", "changelog", "release", "docs")
    )

    # Determine if LLM ranking would help
    needs_ranking = intent_type in ("plan", "debug") or len(query.split()) > 10

    return QueryIntent(
        intent_type=intent_type,
        entities=entities,
        scope=scope,
        time_window="all",
        needs_external=needs_external,
        needs_ranking=needs_ranking,
        needs_consolidation=False,
    )

async def _retrieve_engram(query: str, *args, **kwargs) -> List[ContextItem]:
    """Retrieve decisions and patterns from the Engram store.

    Queries the Engram MCP server for relevant stored decisions,
    patterns, and architectural knowledge.
    """
    results: List[ContextItem] = []
    try:
        from shared.embedding import async_embed
        embedding = await async_embed(query)
        qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
        collection = os.getenv("ENGRAM_COLLECTION", "automem")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{qdrant_url}/collections/{collection}/points/search",
                json={
                    "vector": embedding,
                    "limit": 5,
                    "with_payload": True,
                    "filter": {"must": [{"key": "type", "match": {"value": "decision"}}]}
                },
                timeout=10.0,
            )
            response.raise_for_status()
            points = response.json().get("result", [])
            for p in points:
                results.append(ContextItem(
                    content=p["payload"].get("content", ""),
                    source_name=p["payload"].get("title", "engram"),
                    source_level=p["payload"].get("layer", 4),
                    score=p["score"],
                ))
    except Exception as e:
        print(f"WARNING: Engram retrieval failed: {e}")
    return results

async def _rank_and_fuse(results_by_level: Dict[str, List[ContextItem]], intent: QueryIntent, query: str, llm_fn=None) -> List[ContextItem]:
    """Rank and fuse results from multiple retrieval sources.

    When LLM ranking is needed (intent.needs_ranking), an LLM call function
    must be provided via llm_fn. Without it, falls back to score-based sorting.
    """
    all_items = [item for sublist in results_by_level.values() for item in sublist]
    all_items.sort(key=lambda x: x.score, reverse=True)
    if intent.needs_ranking and llm_fn is not None:
        print("INFO: LLM ranking is enabled for this query.")
        all_items = await rank_by_relevance(query, all_items, llm_fn)
    elif intent.needs_ranking and llm_fn is None:
        print("INFO: LLM ranking requested but no LLM function provided. Using score-based order.")
    return all_items

async def retrieve(query: str, session_type: str = "dev", token_budget: int = 2500) -> ContextPack:
    """
    Main entry point for context retrieval.
    Queries the vector database and assembles a ContextPack.
    """
    intent = classify_intent(query)
    embedding = get_embedding(query)

    results: List[ContextItem] = []
    qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    collection = os.getenv("QDRANT_COLLECTION", "automem")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{qdrant_url}/collections/{collection}/points/search",
                json={
                    "vector": embedding,
                    "limit": 10,
                    "with_payload": True,
                    "filter": {"must": [{"key": "type", "match": {"value": "code_map"}}]}
                },
                timeout=10.0,
            )
            response.raise_for_status()
            points = response.json().get("result", [])
            for p in points:
                results.append(ContextItem(
                    content=p["payload"].get("content", ""),
                    source_name=p["payload"].get("file_path", "unknown"),
                    source_level=p["payload"].get("layer", 1),
                    score=p["score"]
                ))
        except Exception as e:
            print(f"WARNING: Qdrant retrieval failed: {e}")

    fused_items = await _rank_and_fuse({"qdrant": results}, intent, query)

    sections = []
    current_tokens = 0
    for item in fused_items:
        # Approximate token count (1 word ≈ 1.3 tokens)
        item_tokens = int(len(item.content.split()) * 1.3)
        if current_tokens + item_tokens > token_budget:
            break
        sections.append({
            "source": "qdrant",
            "name": item.source_name,
            "content": item.content
        })
        current_tokens += item_tokens

    return ContextPack(
        query=query,
        total_tokens=current_tokens,
        sections=sections
    )
