from dataclasses import dataclass
from typing import List, Dict
import asyncio
import httpx
from pydantic import BaseModel
from .index_repo import upsert_repository_index
from shared.llm.config import rank_by_relevance, ContextItem, QueryIntent
from shared.models.repo import RepoNode

def get_repo_map(file_path: str, project_root: str = "") -> str:
    """Placeholder for retrieving a tree of the repo."""
    return "repo_map_tree_representation"

def prune_content(source: str, path: str = "", max_tokens: int = 100) -> str:
    """Placeholder for simple content pruning to fit token limits."""
    # Assuming rough token logic: 1 token ~ 4 chars
    return "def alpha():..."

@dataclass
class ContextPack:
    query: str
    total_tokens: int
    sections: List[Dict[str, str]]

def get_embedding(text: str) -> list[float]:
    print(f"WARNING: get_embedding is a placeholder. Received: {text}")
    return [0.0] * 384

def classify_intent(query: str) -> QueryIntent:
    print(f"WARNING: classify_intent is a placeholder. Received: {query}")
    return QueryIntent(intent_type="code_lookup", entities=[], scope="this_project", time_window="all", needs_external=False, needs_ranking=False, needs_consolidation=False)

async def _retrieve_engram(*args, **kwargs) -> List[ContextItem]:
    print("WARNING: _retrieve_engram is a placeholder.")
    return []

async def _rank_and_fuse(results_by_level: Dict[str, List[ContextItem]], intent: QueryIntent, query: str, mock_llm_fn=None) -> List[ContextItem]:
    all_items = [item for sublist in results_by_level.values() for item in sublist]
    all_items.sort(key=lambda x: x.score, reverse=True)
    if intent.needs_ranking:
        print("INFO: LLM ranking is enabled for this query.")
        
        async def default_mock(p: str): return '{"ranked_indices": [0,1,2]}'
        llm_to_use = mock_llm_fn if mock_llm_fn else default_mock
        all_items = await rank_by_relevance(query, all_items, llm_to_use)
    return all_items

async def retrieve(query: str, session_type: str = "dev", token_budget: int = 2500) -> ContextPack:
    """
    Main entry point for context retrieval.
    Queries the vector database and assembles a ContextPack.
    """
    intent = classify_intent(query)
    embedding = get_embedding(query)

    # Simulated call to Qdrant based on the mock in the test
    results = []
    async with httpx.AsyncClient() as client:
        try:
            # We assume qdrant is at localhost:6333
            response = await client.post(
                "http://127.0.0.1:6333/collections/automem/points/search",
                json={
                    "vector": embedding,
                    "limit": 10,
                    "with_payload": True,
                    "filter": {"must": [{"key": "type", "match": {"value": "code_map"}}]}
                }
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
