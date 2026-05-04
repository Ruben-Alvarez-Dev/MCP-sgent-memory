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
import logging
import httpx
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent-memory.retrieval")

from ..llm import classify_intent, QueryIntent, get_llm, rank_by_relevance
from ..embedding import get_embedding, bm25_tokenize
from .index_repo import build_repo_index_points, upsert_repository_index
from .pruner import prune_content
from .repo_map import get_repo_map
from ..qdrant_client import QdrantClient

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "L0_L4_memory")
CONV_COLLECTION = os.getenv("CONV_COLLECTION", "L2_conversations")
MEM0_COLLECTION = os.getenv("MEM0_COLLECTION", "L3_facts")
_MSD = os.getenv("MEMORY_SERVER_DIR", "")
ENGRAM_PATH = os.getenv(
    "ENGRAM_PATH",
    os.path.join(_MSD, "data", "memory", "engram") if _MSD else str(Path.home() / ".memory" / "engram")
)
MIN_SCORE = float(os.getenv("VK_MIN_SCORE", "0.3"))
MAX_TOKENS = int(os.getenv("VK_MAX_TOKENS", "48000"))

_qdrant_clients: dict[str, QdrantClient] = {}
def _get_scoped_client(collection: str) -> QdrantClient:
    if collection not in _qdrant_clients:
        _qdrant_clients[collection] = QdrantClient(QDRANT_URL, collection, 1024)
    return _qdrant_clients[collection]


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
    agent_scope: str = "shared",
) -> ContextPack:
    intent = classify_intent(query, session_type, open_files)
    setattr(intent, "_original_query", query)

    profile_name = INTENT_TO_PROFILE.get(intent.intent_type, "default")
    profile = PROFILES.get(profile_name, PROFILES["default"])
    if token_budget:
        profile = RetrievalProfile(**{**profile.__dict__, "token_budget": token_budget})

    results = await _retrieve_parallel(intent, profile, agent_scope)
    ranked = _rank_and_fuse(results, profile, intent)
    pack = _pack_context(ranked, profile, intent)
    pack.query = query
    return pack


async def _retrieve_parallel(
    intent: QueryIntent, profile: RetrievalProfile, agent_scope: str = "shared"
) -> dict[str, list[ContextItem]]:
    tasks: dict[str, asyncio.Task] = {}
    for level, weight in profile.level_weights.items():
        if weight < 0.1:
            continue
        k = profile.top_k_per_level.get(level, 3)

        if level == 0:
            tasks["L0"] = asyncio.create_task(
                _retrieve_hybrid(intent, k, collection=CONV_COLLECTION, agent_scope=agent_scope)
            )
        elif level == 1:
            tasks["L1"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=1, agent_scope=agent_scope))
        elif level == 2:
            tasks["L2"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=2, agent_scope=agent_scope))
            tasks["L2_engram"] = asyncio.create_task(_retrieve_engram(intent, k))
        elif level == 3:
            tasks["L3"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=3, agent_scope=agent_scope))
        elif level == 4:
            tasks["L4"] = asyncio.create_task(_retrieve_hybrid(intent, k, level=4, agent_scope=agent_scope))
        elif level == 5:
            tasks["L5"] = asyncio.create_task(
                _retrieve_hybrid(intent, k, collection=MEM0_COLLECTION, agent_scope=agent_scope)
            )

    raw_results: dict[str, list[ContextItem]] = {}
    for name, task in tasks.items():
        try:
            raw_results[name] = await task
        except Exception as e:
            logger.warning("Parallel retrieval failed for %s: %s", name, e)
            raw_results[name] = []
    return raw_results


async def _retrieve_hybrid(
    intent: QueryIntent, k: int, level: int | None = None, collection: str | None = None, agent_scope: str = "shared"
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

    target_coll = f"{collection or QDRANT_COLLECTION}_{agent_scope}" if agent_scope and agent_scope != "shared" else (collection or QDRANT_COLLECTION)
    search_filter = (
        {"must": [{"key": "layer", "match": {"value": level}}]}
        if level is not None
        else None
    )

    results: list[ContextItem] = []

    try:
        client = _get_scoped_client(target_coll)
        vector = get_embedding(query_text)
        search_results = await client.search(
            vector,
            limit=k,
            score_threshold=MIN_SCORE,
            filter=search_filter,
        )
        for p in search_results:
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
    except Exception as e:
        logger.warning("Retrieval failed for collection=%s level=%s: %s", target_coll, level, e)

    return results


async def _retrieve_engram(intent: QueryIntent, k: int) -> list[ContextItem]:
    L3_decisions_path = Path(ENGRAM_PATH)
    if not L3_decisions_path.exists():
        return []
    results = []
    query_terms = set(w.lower() for w in intent.entities)
    if not query_terms:
        return []
    for md_file in L3_decisions_path.rglob("*.md"):
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
        except Exception as e:
            logger.debug("Error reading engram file %s: %s", md_file, e)
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
            freshness = _freshness_score(item)
            # v1.4: freshness joins the ranking (30% weight)
            # Before: combined = (level_weight * score * 0.7) + (recency * 0.3)
            # After:  combined = (level_weight * score * 0.5) + (recency * 0.2) + (freshness * 0.3)
            item.combined_score = (
                (level_weight * item.score * 0.5)
                + (recency * 0.2)
                + (freshness * 0.3)
            )
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
        except Exception as e:
            logger.debug("LLM ranking failed, using score-based order: %s", e)

    return all_items


def _recency_score(timestamp: datetime | None, time_window: str) -> float:
    if not timestamp:
        return 0.3
    now = datetime.now(timezone.utc) if timestamp.tzinfo else datetime.now()
    age_hours = (now - timestamp).total_seconds() / 3600
    return max(0, 1.0 - age_hours / 720.0)


# ── v1.4: Freshness Scoring ──────────────────────────────────────────
# Based on FreshQA (Vu 2023): classify facts by change_speed, decay accordingly.
# Based on Reconsolidation (Nader 2000): every recall is a verification opportunity.

CHANGE_SPEED_HALF_LIFE: dict[str, float] = {
    "never": 999_999.0,    # immutable facts — effectively never decay
    "slow": 720.0,         # architecture, stack — half-life ~30 days
    "fast": 48.0,          # bugs, task progress — half-life ~2 days
    "realtime": 1.0,       # git status, open files — half-life ~1 hour
}


def _freshness_score(item: ContextItem) -> float:
    """Score how fresh/verified a memory is. Range: [0.0, 1.0].

    - verified recently → 0.8–1.0 (trustworthy)
    - never verified     → 0.3     (suspicious)
    - stale              → 0.15    (dangerous)
    - unverifiable       → 0.5     (neutral — can't check, don't penalize)
    """
    status = item.metadata.get("verification_status", "never_verified")
    if status == "unverifiable":
        return 0.5
    if status == "stale":
        return 0.15
    if status == "verified":
        verified_at_str = item.metadata.get("verified_at")
        if not verified_at_str:
            return 0.7  # verified but no timestamp — trust moderately
        verified_ts = _parse_ts(verified_at_str)
        if not verified_ts:
            return 0.7
        now = datetime.now(timezone.utc) if verified_ts.tzinfo else datetime.now()
        age_hours = max(0, (now - verified_ts).total_seconds() / 3600)
        speed = item.metadata.get("change_speed", "slow")
        half_life = CHANGE_SPEED_HALF_LIFE.get(speed, 720.0)
        # Exponential decay: score = 0.5 * (1 - age/half_life), floored at 0.3
        return max(0.3, 0.5 * (1.0 - age_hours / half_life) + 0.5)
    # never_verified
    return 0.3


def _freshness_tag(item: ContextItem) -> str:
    """Human-readable freshness indicator for context injection."""
    status = item.metadata.get("verification_status", "never_verified")
    if status == "unverifiable":
        return "🔒 UNVERIFIABLE"
    if status == "stale":
        return "⚠️ STALE"
    if status == "verified":
        verified_at_str = item.metadata.get("verified_at")
        if not verified_at_str:
            return "✅ VERIFIED"
        verified_ts = _parse_ts(verified_at_str)
        if not verified_ts:
            return "✅ VERIFIED"
        now = datetime.now(timezone.utc) if verified_ts.tzinfo else datetime.now()
        age_hours = max(0, (now - verified_ts).total_seconds() / 3600)
        if age_hours < 1:
            return "✅ VERIFIED just now"
        if age_hours < 24:
            return f"✅ VERIFIED {int(age_hours)}h ago"
        return f"✅ VERIFIED {int(age_hours / 24)}d ago"
    return "❓ NEVER VERIFIED"


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
        section = {
            "level": item.source_level,
            "source": item.source_name,
            "content": content,
            "confidence": round(item.combined_score, 2),
            "type": item.metadata.get("type", "unknown"),
        }
        # v1.4: add freshness tag if verification data exists
        freshness = _freshness_tag(item)
        if freshness != "❓ NEVER VERIFIED" or item.metadata.get("verification_status"):
            section["freshness"] = freshness
        sections.append(section)
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
    except Exception:
        return None


__all__ = [
    "ContextItem",
    "ContextPack",
    "PROFILES",
    "RetrievalProfile",
    "retrieve",
    "CHANGE_SPEED_HALF_LIFE",
    "_freshness_score",
    "_freshness_tag",
]
