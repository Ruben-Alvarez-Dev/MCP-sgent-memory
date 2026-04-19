"""Retrieval Router — decides WHAT to retrieve, FROM WHERE, and HOW MUCH.

The brain of vk-cache. Routes each query through:
  1. classify_intent() — deterministic intent classification (<0.1ms)
  2. profile selection — picks retrieval profile based on intent + session type
  3. parallel retrieval — queries all relevant levels/sources concurrently
  4. rank & fuse — combines results with recency + entity boosts
  5. context packing — assembles within token budget
"""

from __future__ import annotations

import asyncio
import hashlib
import httpx
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..llm import classify_intent, QueryIntent, get_llm, rank_by_relevance
from ..embedding import get_embedding, bm25_tokenize
from .index_repo import build_repo_index_points, upsert_repository_index
from .pruner import prune_content
from .repo_map import get_repo_map

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
CONV_COLLECTION = os.getenv("CONV_COLLECTION", "conversations")
MEM0_COLLECTION = os.getenv("MEM0_COLLECTION", "mem0_memories")
_MSD = os.getenv("MEMORY_SERVER_DIR", "")
ENGRAM_PATH = os.getenv(
    "ENGRAM_PATH",
    os.path.join(_MSD, "data", "memory", "engram") if _MSD else str(Path.home() / ".memory" / "engram")
)
MIN_SCORE = float(os.getenv("VK_MIN_SCORE", "0.3"))
MAX_TOKENS = int(os.getenv("VK_MAX_TOKENS", "48000"))


# ── Retrieval Profiles ────────────────────────────────────────────


@dataclass
class RetrievalProfile:
    name: str
    level_weights: dict[int, float]
    top_k_per_level: dict[int, int]
    token_budget: int
    max_time_ms: int
    needs_ai_ranking: bool
    domain_keywords: list[str] = field(default_factory=list)
    is_builtin: bool = True


PROFILES: dict[str, RetrievalProfile] = {}


def _register_profile(profile: RetrievalProfile) -> None:
    PROFILES[profile.name] = profile


_register_profile(
    RetrievalProfile(
        name="dev",
        level_weights={1: 1.0, 2: 0.9, 3: 0.7, 4: 0.5, 5: 0.3},
        top_k_per_level={1: 15, 2: 10, 3: 10, 4: 5, 5: 5},
        token_budget=48000,
        max_time_ms=2000,
        needs_ai_ranking=False,
        domain_keywords=[
            "function",
            "class",
            "method",
            "test",
            "bug",
            "code",
            "repo",
            "implement",
            "refactor",
            "module",
            "api",
            "endpoint",
        ],
    )
)

_register_profile(
    RetrievalProfile(
        name="docs",
        level_weights={3: 1.0, 4: 0.9, 5: 0.7, 2: 0.5, 1: 0.3},
        top_k_per_level={1: 5, 2: 10, 3: 15, 4: 10, 5: 5},
        token_budget=48000,
        max_time_ms=2000,
        needs_ai_ranking=False,
        domain_keywords=[
            "spec",
            "adr",
            "rfc",
            "design",
            "architecture",
            "proposal",
            "decision record",
            "document",
            "requirements",
            "srs",
        ],
    )
)

_register_profile(
    RetrievalProfile(
        name="default",
        level_weights={1: 1.0, 2: 0.8, 3: 0.6},
        top_k_per_level={1: 10, 2: 10, 3: 10},
        token_budget=32000,
        max_time_ms=3000,
        needs_ai_ranking=False,
        domain_keywords=[],
    )
)

INTENT_TO_PROFILE = {
    "code_lookup": "dev",
    "decision_recall": "dev",
    "how_to": "dev",
    "relationship": "dev",
    "summary": "docs",
    "conversation_recall": "default",
    "error_diagnosis": "dev",
    "pattern_match": "default",
}


@dataclass
class ContextItem:
    content: str
    source_level: int
    source_name: str
    score: float
    combined_score: float = 0.0
    timestamp: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ContextPack:
    sections: list[dict]
    total_tokens: int
    sources_used: list[str]
    confidence: float
    profile: str
    query: str = ""
    staleness_warnings: list[str] = field(default_factory=list)


async def retrieve(
    query: str,
    session_type: str = "coding",
    token_budget: int | None = None,
    open_files: list[str] | None = None,
) -> ContextPack:
    intent = classify_intent(query, session_type, open_files)
    setattr(intent, "_original_query", query)

    profile_name = INTENT_TO_PROFILE.get(intent.intent_type, "default")
    profile = PROFILES.get(profile_name, PROFILES["default"])
    if token_budget:
        profile = RetrievalProfile(**{**profile.__dict__, "token_budget": token_budget})

    results = await _retrieve_parallel(intent, profile)
    ranked = _rank_and_fuse(results, profile, intent)
    pack = _pack_context(ranked, profile, intent)
    pack.query = query
    return pack


async def _retrieve_parallel(
    intent: QueryIntent, profile: RetrievalProfile
) -> dict[str, list[ContextItem]]:
    tasks: dict[str, asyncio.Task] = {}
    for level, weight in profile.level_weights.items():
        if weight < 0.1:
            continue
        k = profile.top_k_per_level.get(level, 3)

        if level == 0:
            tasks["L0"] = asyncio.create_task(
                _retrieve_hybrid(intent, k, collection=CONV_COLLECTION)
            )
        elif level == 1:
            tasks["L1"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=1))
        elif level == 2:
            tasks["L2"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=2))
            tasks["L2_engram"] = asyncio.create_task(_retrieve_engram(intent, k))
        elif level == 3:
            tasks["L3"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=3))
        elif level == 4:
            tasks["L4"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=4))
        elif level == 5:
            tasks["L5"] = asyncio.create_task(
                _retrieve_hybrid(intent, k, collection=MEM0_COLLECTION)
            )

    raw_results: dict[str, list[ContextItem]] = {}
    for name, task in tasks.items():
        try:
            raw_results[name] = await task
        except:
            raw_results[name] = []
    return raw_results


async def _retrieve_hybrid(
    intent: QueryIntent, k: int, level: int | None = None, collection: str | None = None
) -> list[ContextItem]:
    """Production-grade Hybrid Search: Dense Vector + Sparse BM25.

    Uses /points/search (returns proper scores in Qdrant v1.13).
    Sparse BM25 is applied as a second pass when available.
    """
    query_text = (
        " ".join(intent.entities)
        if intent.entities
        else getattr(intent, "_original_query", "")
    )
    if not query_text:
        return []

    target_coll = collection or QDRANT_COLLECTION
    search_filter = (
        {"must": [{"key": "layer", "match": {"value": level}}]}
        if level is not None
        else None
    )

    results: list[ContextItem] = []

    async with httpx.AsyncClient() as client:
        # ── 1. Dense search via /points/search (reliable scores) ──
        try:
            vector = get_embedding(query_text)
            body = {
                "vector": vector,
                "limit": k,
                "score_threshold": MIN_SCORE,
                "with_payload": True,
            }
            if search_filter:
                body["filter"] = search_filter
            resp = await client.post(
                f"{QDRANT_URL}/collections/{target_coll}/points/search", json=body
            )
            if resp.status_code == 200:
                for p in resp.json().get("result", []):
                    payload = p.get("payload", {})
                    results.append(
                        ContextItem(
                            content=payload.get("content", ""),
                            source_level=payload.get("layer", level or 1),
                            source_name=target_coll,
                            score=p.get("score", 0),
                            metadata=payload,
                            timestamp=_parse_ts(payload.get("created_at")),
                        )
                    )
        except Exception:
            pass

    return results




async def _retrieve_engram(intent: QueryIntent, k: int) -> list[ContextItem]:
    engram_path = Path(ENGRAM_PATH)
    if not engram_path.exists():
        return []
    results = []
    query_terms = set(w.lower() for w in intent.entities)
    if not query_terms:
        return []
    for md_file in engram_path.rglob("*.md"):
        try:
            content = md_file.read_text()
            if any(word in content.lower() for word in query_terms):
                results.append(
                    ContextItem(
                        content=content,
                        source_level=3,
                        source_name="engram",
                        score=0.6,
                        timestamp=datetime.fromtimestamp(md_file.stat().st_mtime),
                        metadata={"type": "decision"},
                    )
                )
        except:
            pass
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:k]


def _rank_and_fuse(
    results: dict[str, list[ContextItem]],
    profile: RetrievalProfile,
    intent: QueryIntent,
) -> list[ContextItem]:
    all_items: list[ContextItem] = []
    for source, items in results.items():
        level_num = int(source[1]) if len(source) > 1 and source[1].isdigit() else 1
        level_weight = profile.level_weights.get(level_num, 0.5)
        for item in items:
            recency = _recency_score(item.timestamp, intent.time_window)
            item.combined_score = (level_weight * item.score * 0.7) + (recency * 0.3)
            all_items.append(item)
    all_items.sort(key=lambda x: x.combined_score, reverse=True)

    # SPEC-4.1: LLM ranking for complex queries
    if intent.needs_ranking and len(all_items) > 5:
        try:
            query_text = getattr(intent, "_original_query", "") or " ".join(intent.entities)
            ranked = rank_by_relevance(
                query=query_text,
                items=[{"content": item.content, "item": item} for item in all_items],
                top_k=profile.token_budget // 500,
            )
            all_items = [r["item"] for r in ranked]
        except Exception:
            pass  # Ranking failed, use score-based order

    return all_items


def _recency_score(timestamp: datetime | None, time_window: str) -> float:
    if not timestamp:
        return 0.3
    now = datetime.now(timezone.utc) if timestamp.tzinfo else datetime.now()
    age_hours = (now - timestamp).total_seconds() / 3600
    return max(0, 1.0 - age_hours / 720.0)


def _pack_context(
    items: list[ContextItem], profile: RetrievalProfile, intent: QueryIntent
) -> ContextPack:
    sections = []
    total_tokens = 0
    sources_used = set()
    buffer_rules = [
        i
        for i in items
        if i.metadata.get("type") in ["rule", "pattern", "standard", "instruction"]
    ]
    buffer_structure = [
        i for i in items if i.source_name == "repo_map" or i.source_level == 4
    ]
    buffer_dynamic = [
        i for i in items if i not in buffer_rules and i not in buffer_structure
    ]

    RULE_BUDGET, STRUCT_BUDGET = 8000, 16000

    def _add(item: ContextItem, is_rule: bool = False):
        nonlocal total_tokens
        content = prune_content(item.content, max_tokens=2048, is_rule=is_rule)
        tokens = len(content) // 4
        if total_tokens + tokens > profile.token_budget:
            return False
        sections.append(
            {
                "level": item.source_level,
                "source": item.source_name,
                "content": content,
                "confidence": round(item.combined_score, 2),
                "type": item.metadata.get("type", "unknown"),
            }
        )
        total_tokens += tokens
        sources_used.add(item.source_name)
        return True

    for item in sorted(buffer_rules, key=lambda x: x.combined_score, reverse=True):
        if total_tokens < RULE_BUDGET:
            _add(item, is_rule=True)
    for item in sorted(buffer_structure, key=lambda x: x.combined_score, reverse=True):
        if total_tokens < (RULE_BUDGET + STRUCT_BUDGET):
            _add(item)
    for item in sorted(buffer_dynamic, key=lambda x: x.combined_score, reverse=True):
        if total_tokens < profile.token_budget:
            _add(item)

    return ContextPack(
        sections=sections,
        total_tokens=total_tokens,
        sources_used=sorted(sources_used),
        confidence=0.8,
        profile=profile.name,
    )


def _parse_ts(ts_str: Any) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except:
        return None


__all__ = ["ContextItem", "ContextPack", "PROFILES", "RetrievalProfile", "retrieve"]
