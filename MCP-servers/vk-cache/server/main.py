"""vk-cache — Unified Retrieval & Context Assembly (L5).

The brain of the memory system. Implements the BIDIRECTIONAL protocol:

  PULL: LLM requests context → returns ContextPack
  PUSH: System detects need → sends ContextReminder

This server does NOT store data. It queries:
  - Qdrant (via automem collection)
  - Engram (via filesystem/API)
  - mem0-bridge
  - conversation-store

Works with or without the LLM connected.
Embeddings via llama.cpp (self-contained).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.env_loader import load_env
load_env()
from shared.models import (
    ContextPack,
    ContextReminder,
    ContextRequest,
    ContextSource,
    MemoryLayer,
)

# Embedding via llama.cpp
from shared.embedding import get_embedding as llama_embed, _ensure_binaries as _ensure_llama

# Retrieval router
from shared.retrieval import retrieve as smart_retrieve
from shared.retrieval import get_repo_map, prune_content

# Compliance verifier
from shared.compliance import verify_compliance, add_rule, ProjectRule

mcp = FastMCP("vk-cache")

# ── Configuration ──────────────────────────────────────────────────

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "automem")
MIN_SCORE = float(os.getenv("VK_MIN_SCORE", "0.3"))
MAX_ITEMS = int(os.getenv("VK_MAX_ITEMS", "8"))
MAX_TOKENS = int(os.getenv("VK_MAX_TOKENS", "8000"))

# State
_reminders_path = Path.home() / ".memory" / "reminders"
_reminders_path.mkdir(parents=True, exist_ok=True)


# ── Embedding ─────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    """Generate embedding via llama.cpp (self-contained)."""
    _ensure_llama()
    return await asyncio.to_thread(llama_embed, text)


# ── Retrieval from all sources ─────────────────────────────────────

async def search_qdrant(query: str, limit: int = 10) -> list[dict]:
    """Search Qdrant for relevant memories."""
    vector = await embed_text(query)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
            json={
                "vector": vector,
                "limit": limit,
                "score_threshold": MIN_SCORE,
                "with_payload": True,
            },
        )
        if resp.status_code != 200:
            return []
        result_data = resp.json().get("result", [])
        # Qdrant v1.13+ returns list directly, older nest under "result"
        points = result_data if isinstance(result_data, list) else result_data.get("result", [])
        return [
            {
                "source": "qdrant",
                "score": p.get("score", 0),
                "memory_id": p["id"],
                "content": p.get("payload", {}).get("content", ""),
                "layer": p.get("payload", {}).get("layer", 0),
                "type": p.get("payload", {}).get("type", ""),
                "scope": f"{p.get('payload', {}).get('scope_type', '')}/{p.get('payload', {}).get('scope_id', '')}",
            }
            for p in points
        ]


async def search_engram(query: str, limit: int = 5) -> list[dict]:
    """Search Engram (filesystem-based semantic memory)."""
    engram_path = Path(os.getenv("ENGRAM_PATH", str(Path.home() / ".memory" / "engram")))
    if not engram_path.exists():
        return []

    results = []
    query_terms = query.lower().split()[:5]
    for md_file in engram_path.rglob("*.md"):
        try:
            content = md_file.read_text()
            if any(word in content.lower() for word in query_terms):
                results.append({
                    "source": "engram",
                    "score": 0.6,
                    "memory_id": f"engram:{md_file.name}",
                    "content": content[:500],
                    "layer": 3,
                    "type": "decision",
                    "scope": "agent/engram",
                })
        except Exception:
            pass

    return results[:limit]


async def _compress_results(results: list[dict], max_items: int) -> list[dict]:
    """Deduplicate and rank results."""
    seen: set[str] = set()
    unique = []
    for r in results:
        h = hashlib.md5(r["content"][:100].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(r)

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:max_items]


def _build_summary(results: list[dict]) -> str:
    """Build a compressed briefing from ranked results."""
    if not results:
        return "No relevant context found."

    parts: list[str] = []
    for r in results:
        layer_names = {0: "RAW", 1: "WORKING", 2: "EPISODIC", 3: "SEMANTIC", 4: "CONSOLIDATED"}
        layer_name = layer_names.get(r.get("layer", 0), f"L{r.get('layer', '?')}")
        parts.append(
            f"[{layer_name}] [{r['score']:.2f}] ({r['scope']}): {r['content'][:200]}"
        )
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars ≈ 1 token)."""
    return len(text) // 4


def _maybe_repo_section(query: str) -> dict[str, Any] | None:
    repo_map = get_repo_map(query)
    if not repo_map:
        return None

    content = prune_content(repo_map["summary"], path=repo_map["root"]["path"], max_tokens=256)
    return {
        "level": 5,
        "source": "repo-map",
        "content": content,
        "confidence": 0.95,
        "bonus": False,
        "repo_map": repo_map,
    }


# ── Reminder tracking ─────────────────────────────────────────────

def _save_reminder(reminder: ContextReminder):
    path = _reminders_path / f"{reminder.reminder_id}.json"
    path.write_text(reminder.model_dump_json(indent=2))


def _get_active_reminders(agent_id: str) -> list[ContextReminder]:
    reminders = []
    for f in _reminders_path.glob("*.json"):
        data = json.loads(f.read_text())
        reminder = ContextReminder(**data)
        if reminder.pack.sources:
            reminders.append(reminder)
    return reminders


# ── Public MCP Tools (Bidirectional Protocol) ─────────────────────


@mcp.tool()
async def request_context(
    query: str,
    agent_id: str = "default",
    intent: str = "answer",
    token_budget: int = 8000,
    scopes: str = "",
) -> str:
    """LLM requests context. Returns a ContextPack with smart routing.

    This is the PULL side of the bidirectional protocol.
    Uses the retrieval router to intelligently select:
      - Which memory levels to query (0-5)
      - How many items per level
      - Whether to use AI ranking
      - Token budget allocation

    Args:
        query: What context is needed.
        agent_id: Which agent is asking.
        intent: answer | plan | review | debug | study
        token_budget: Max tokens for returned context.
        scopes: Comma-separated allowed scopes.
    """
    # Map intent to session type for the router
    session_type_map = {
        "answer": "dev",
        "plan": "dev",
        "review": "dev",
        "debug": "ops",
        "study": "docs",
    }
    session_type = session_type_map.get(intent, "dev")

    # Use the smart retrieval router
    pack = await smart_retrieve(
        query=query,
        session_type=session_type,
        token_budget=token_budget,
    )

    repo_section = _maybe_repo_section(query)
    if repo_section:
        pack.sections.insert(0, repo_section)
        pack.sources_used = sorted(set(pack.sources_used + ["repo-map"]))
        pack.total_tokens += _estimate_tokens(repo_section["content"])

    # Convert to the legacy ContextPack format for backwards compatibility
    sources = [
        ContextSource(
            scope=s.get("source", ""),
            layer=s.get("level", 0),
            mem_type="",
            score=s.get("confidence", 0),
            memory_id="",
            content_preview=s.get("content", "")[:500],
        )
        for s in pack.sections
    ]

    # Build summary from sections
    parts = []
    for s in pack.sections:
        level_names = {0: "RAW", 1: "COMMITTABLE", 2: "ENTITIES", 3: "IDEAS", 4: "FUNCTIONAL", 5: "TRUTHS"}
        level_name = level_names.get(s.get("level", 0), f"L{s.get('level', '?')}")
        bonus_tag = " [BONUS]" if s.get("bonus") else ""
        parts.append(
            f"[{level_name}/{s.get('source', '?')}]{bonus_tag} (conf={s.get('confidence', 0):.2f}): {s.get('content', '')[:200]}"
        )
    summary = "\n".join(parts) if parts else "No relevant context found."

    legacy_pack = ContextPack(
        request_id="",
        query=query,
        sources=sources,
        summary=summary,
        citations=[],
        token_estimate=pack.total_tokens,
        reason=f"smart_retrieve:{pack.profile}",
    )

    return json.dumps({
        "context_pack": legacy_pack.model_dump(mode="json"),
        "injection_text": legacy_pack.to_injection_text(),
        "metadata": {
            "profile": pack.profile,
            "sections_returned": len(pack.sections),
            "sources_used": pack.sources_used,
            "token_estimate": pack.total_tokens,
            "within_budget": pack.total_tokens <= token_budget,
            "confidence": pack.confidence,
            "staleness_warnings": pack.staleness_warnings,
        },
    }, indent=2)


@mcp.tool()
async def check_reminders(agent_id: str = "default") -> str:
    """Check if there are pending context reminders for this agent."""
    reminders = _get_active_reminders(agent_id)
    if not reminders:
        return json.dumps({
            "agent_id": agent_id,
            "reminders": [],
            "message": "No pending reminders",
        }, indent=2)

    result = []
    for r in reminders:
        result.append({
            "reminder_id": r.reminder_id,
            "reason": r.reason,
            "expires_after_turns": r.expires_after_turns,
            "pack": r.pack.to_injection_text(),
        })

    return json.dumps({
        "agent_id": agent_id,
        "reminders": result,
        "count": len(result),
    }, indent=2)


@mcp.tool()
async def push_reminder(
    query: str,
    reason: str = "relevant_to_current_task",
    agent_id: str = "default",
) -> str:
    """System pushes a context reminder to the LLM."""
    results = await search_qdrant(query, limit=5)
    ranked = await _compress_results(results, 5)
    summary = _build_summary(ranked)

    repo_section = _maybe_repo_section(query)
    if repo_section:
        summary = f"[REPO-MAP] [0.95] (repo-map): {repo_section['content']}\n{summary}"

    sources = [
        ContextSource(
            scope=r.get("scope", ""),
            layer=r.get("layer", 0),
            mem_type=r.get("type", ""),
            score=r.get("score", 0),
            memory_id=r.get("memory_id", ""),
            content_preview=r.get("content", "")[:500],
        )
        for r in ranked
    ]

    pack = ContextPack(
        request_id="",
        query=query,
        sources=sources,
        summary=summary,
        citations=[s.memory_id for s in sources if s.memory_id],
        token_estimate=_estimate_tokens(summary),
        reason=reason,
    )

    reminder = ContextReminder(pack=pack, reason=reason)
    _save_reminder(reminder)

    return json.dumps({
        "status": "reminder_pushed",
        "reminder_id": reminder.reminder_id,
        "reason": reason,
        "sources": len(sources),
    }, indent=2)


@mcp.tool()
async def dismiss_reminder(reminder_id: str) -> str:
    """Dismiss a reminder — the LLM used it or it's not relevant."""
    path = _reminders_path / f"{reminder_id}.json"
    if path.exists():
        path.unlink()
        return json.dumps({"status": "dismissed", "reminder_id": reminder_id}, indent=2)
    return json.dumps({"status": "not_found", "reminder_id": reminder_id}, indent=2)


@mcp.tool()
async def detect_context_shift(
    current_query: str,
    previous_query: str = "",
    agent_id: str = "default",
) -> str:
    """Detect if the conversation context has shifted domains."""
    if not previous_query:
        return json.dumps({"shift_detected": False, "message": "No previous query to compare"}, indent=2)

    # Compare embeddings to detect shift
    try:
        v1 = await embed_text(current_query)
        v2 = await embed_text(previous_query)

        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(a * a for a in v2))
        similarity = dot / (norm1 * norm2) if norm1 and norm2 else 0
    except Exception:
        similarity = 0.0

    shifted = similarity < 0.7

    result = {"shift_detected": shifted, "similarity": round(similarity, 4)}

    if shifted:
        results = await search_qdrant(current_query, limit=5)
        ranked = await _compress_results(results, 5)
        summary = _build_summary(ranked)

        result["new_context"] = summary
        result["auto_reminder"] = True

        sources = [
            ContextSource(
                scope=r.get("scope", ""),
                layer=r.get("layer", 0),
                mem_type=r.get("type", ""),
                score=r.get("score", 0),
                memory_id=r.get("memory_id", ""),
                content_preview=r.get("content", "")[:500],
            )
            for r in ranked
        ]
        pack = ContextPack(
            request_id="",
            query=current_query,
            sources=sources,
            summary=summary,
            citations=[s.memory_id for s in sources if s.memory_id],
            token_estimate=_estimate_tokens(summary),
            reason="domain_change_detected",
        )
        reminder = ContextReminder(pack=pack, reason="domain_change_detected")
        _save_reminder(reminder)

    return json.dumps(result, indent=2)


@mcp.tool()
async def status() -> str:
    """Show vk-cache router status."""
    sources = {}

    # Qdrant
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{QDRANT_URL}/collections")
            sources["qdrant"] = "OK"
    except Exception:
        sources["qdrant"] = "DOWN"

    # Engram
    engram_path = Path(os.getenv("ENGRAM_PATH", str(Path.home() / ".memory/engram")))
    sources["engram"] = "OK" if engram_path.exists() else "NOT_CONFIGURED"

    # llama.cpp
    llama_ok = False
    try:
        from shared.embedding import _get_llama_cmd
        llama_ok = _get_llama_cmd() is not None
    except Exception:
        pass
    sources["llama_cpp"] = "OK" if llama_ok else "NOT_INSTALLED"

    # Active reminders
    reminders = list(_reminders_path.glob("*.json"))

    return json.dumps({
        "daemon": "vk-cache",
        "status": "RUNNING",
        "sources": sources,
        "active_reminders": len(reminders),
        "config": {
            "min_score": MIN_SCORE,
            "max_items": MAX_ITEMS,
            "max_tokens": MAX_TOKENS,
        },
        "note": "Bidirectional protocol: LLM can pull, system can push",
    }, indent=2)


@mcp.tool()
async def verify_compliance_tool(
    code: str,
    rule_ids: str = "",
) -> str:
    """Verify code against project compliance rules.

    Checks for: Pydantic V2 config, secrets in code, datetime.utcnow(),
    bare excepts, eval/exec, input validation.

    Args:
        code: The code to verify.
        rule_ids: Comma-separated rule IDs to check (empty = all rules).
    """
    from shared.compliance import verify_compliance, DEFAULT_RULES

    # Filter rules if specific IDs requested
    rules = DEFAULT_RULES
    if rule_ids.strip():
        requested = set(r.strip() for r in rule_ids.split(","))
        rules = [r for r in DEFAULT_RULES if r.id in requested]

    result = await verify_compliance(code, rules)

    if result.compliant:
        return json.dumps({
            "status": "COMPLIANT",
            "rules_checked": len(result.checked_rules),
            "deterministic_checks": result.deterministic_checks,
            "semantic_checks": result.semantic_checks,
        }, indent=2)

    violations = [
        {
            "rule": v.rule_id,
            "severity": v.severity,
            "detail": v.detail,
            "line": v.line_number,
        }
        for v in result.violations
    ]

    return json.dumps({
        "status": "VIOLATIONS_FOUND",
        "count": len(violations),
        "violations": violations,
    }, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
