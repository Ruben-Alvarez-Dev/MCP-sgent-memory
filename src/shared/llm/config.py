from __future__ import annotations
from pydantic import BaseModel
from typing import List, Coroutine, Callable, Any
import json

class QueryIntent(BaseModel):
    intent_type: str
    entities: List[str]
    scope: str
    time_window: str
    needs_external: bool
    needs_ranking: bool
    needs_consolidation: bool

class ContextItem(BaseModel):
    content: str
    source_name: str
    source_level: int
    score: float
    metadata: dict = {}

async def rank_by_relevance(
    query: str, 
    items: List[ContextItem], 
    llm_call_fn: Callable[[str], Coroutine[None, None, str]],
    top_k: int = 10
) -> List[ContextItem]:
    """
    Ranks items by relevance using a structured JSON prompt to ensure determinism.
    Replaces the fragile regex parser with robust json.loads().
    """
    if not items or len(items) <= 1:
        return items[:top_k]

    prompt = f"Query: '{query}'. Rank the following items by relevance.\n"
    prompt += "You MUST return ONLY valid JSON in this exact format: {\"ranked_indices\": [int, int, ...]}\n\n"
    for i, item in enumerate(items):
        # Truncate content to avoid overwhelming the ranking LLM
        prompt += f"Item {i}:\n{item.content[:200].strip()}...\n\n"

    try:
        response = await llm_call_fn(prompt)
        
        # Clean the response to ensure it's just JSON (in case the LLM wrapped it in markdown)
        json_str = response.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        
        parsed_response = json.loads(json_str.strip())
        
        if "ranked_indices" not in parsed_response or not isinstance(parsed_response["ranked_indices"], list):
             raise ValueError("JSON response missing 'ranked_indices' array.")

        ranked_indices = [int(i) for i in parsed_response["ranked_indices"]]
        
        final_list = []
        seen_indices = set()
        
        # 1. Add ranked items in order
        for index in ranked_indices:
            if index < len(items) and index not in seen_indices:
                final_list.append(items[index])
                seen_indices.add(index)
        
        # 2. Add unranked items (preserving original order)
        for i, item in enumerate(items):
            if i not in seen_indices:
                final_list.append(item)
                
        return final_list[:top_k]
        
    except json.JSONDecodeError as e:
        print(f"WARNING: LLM ranking failed JSON parsing: {e}. Response was: {response[:50]}... Falling back to original score order.")
        return items[:top_k]
    except Exception as e:
        print(f"WARNING: LLM ranking failed: {e}. Falling back to original score order.")
        return items[:top_k]
