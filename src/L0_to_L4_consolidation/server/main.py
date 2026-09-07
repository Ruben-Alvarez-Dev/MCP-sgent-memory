"""L0_to_L4_consolidation — Consolidation & Dream Daemon (M2-storage port).

Storage is shared.memory_db.MemoryDB (SQLite, collection 'L0_L4_memory').

ISO-06 (M2): the cross-layer promotions that minted scope-global rows —
L2→L3 (scope_id='consolidated'), L3→L4 (scope_id='narrative') and the dream
cycle (scope_id='dream') — are hard NO-OPS: they log a warning, report
status='disabled', and never write.

Layer-keyed reads: 'layer' is NOT an engine-filterable key (ISO-11 allowlist
is {agent_scope, user_id} only) and Python post-filtering is forbidden
(ISO-05). Maintenance reads therefore use a documented, same-process,
READ-ONLY administrative SQL cursor with the layer predicate INSIDE the
statement (json_extract + bound parameters) — no user input reaches it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from shared.env_loader import load_env

load_env()
from shared.config import Config
from shared.consolidation import consolidate_l2_l3, consolidate_l3_l4, run_consolidation
from shared.memory_db import MemoryDB
from shared.models import MemoryItem, MemoryLayer, MemoryScope, MemoryType
from shared.result_models import ConsolidateResult, ConsolidationStatusResult, HeartbeatResult, LayerResult

logger = logging.getLogger(__name__)

config = Config.from_env()
db = MemoryDB(None, "L0_L4_memory", config.embedding_dim)
from shared.identity import bind_identity

IDENTITY = bind_identity()  # M4/M5: gate del trunk
DREAM_PATH = Path(config.L4_narrative_path) if config.L4_narrative_path else Path("")
_state_path = DREAM_PATH / "state.json"
_state_path.parent.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("L0_to_L4_consolidation")


def _load_state() -> dict:
    if _state_path.exists():
        return json.loads(_state_path.read_text())
    return {"last_promote_l1_l2": 0, "last_promote_l2_l3": 0, "last_promote_l3_l4": 0, "last_dream": 0, "turn_count": 0, "total_consolidated": 0, "total_dreams": 0}

def _save_state(state: dict) -> None:
    _state_path.write_text(json.dumps(state, indent=2))


def _payloads(rows) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        try:
            out.append(json.loads(row["payload"]))
        except json.JSONDecodeError:
            logger.warning("administrative read: skipped corrupt payload id=%s", row["id"])
    return out


def _admin_read_by_layer(layer: int, limit: int) -> list[dict]:
    """Administrative internal READ-ONLY scan keyed by payload layer.

    'layer' is not an engine-filterable key (ISO-11 allowlist: agent_scope,
    user_id only) and Python post-filtering is forbidden (ISO-05), so this
    same-process maintenance path goes straight to the SQLite cursor with the
    layer predicate INSIDE the SQL statement (json_extract, bound parameter).
    No user input flows into this query; read-only by construction.
    """
    rows = db._conn.execute(
        "SELECT id, payload FROM points "
        "WHERE collection=? AND json_extract(payload, '$.layer')=? LIMIT ?",
        (db.collection, int(layer), int(limit)),
    ).fetchall()
    return _payloads(rows)


async def _promote_l1_l2(state: dict) -> str | None:
    if state["turn_count"] - state.get("last_promote_l1_l2", 0) < config.consolidation_promote_L1:
        return None
    await db.ensure_collection()
    working = _admin_read_by_layer(1, 100)
    if not working:
        return None
    groups: dict[str, list] = {}
    for m in working:
        key = f"{m.get('scope_type', '')}/{m.get('scope_id', '')}"
        groups.setdefault(key, []).append(m)
    batch_points = []
    episode_ids = []
    for scope_key, items in groups.items():
        if len(items) < 2:
            continue
        combined = "\n".join(f"- {m['content']}" for m in items[:10])
        avg_imp = sum(m.get("importance", 0) for m in items) / len(items)
        ep = MemoryItem(layer=MemoryLayer.EPISODIC, scope_type=items[0].get("scope_type", MemoryScope.AGENT), scope_id=items[0].get("scope_id", "system"), type=MemoryType.EPISODE, content=f"Episode ({len(items)} events):\n{combined}", importance=avg_imp, confidence=0.7)
        payload = ep.model_dump(mode="json")
        payload["agent_scope"] = items[0].get("agent_scope", "shared")  # episodes inherit source scope
        vector = None
        batch_points.append({"id": ep.memory_id, "vector": vector, "payload": payload})
        episode_ids.append(ep.memory_id)
    if batch_points:
        await db.upsert_batch(batch_points)
    state["last_promote_l1_l2"] = state.get("turn_count", 0)
    return f"Created {len(episode_ids)} episodes" if episode_ids else None


# ── ISO-06 (M2): scope-global promotions are hard no-ops ──────────────

async def _promote_l2_l3(state: dict, now: float) -> dict:
    """L2→L3: Extract entities from L2 episodes into L3 semantic points."""
    entity_ids = await consolidate_l2_l3(db)
    if entity_ids:
        return {"status": "promoted", "entities": len(entity_ids)}
    return {"status": "no_new_entities"}

async def _promote_l3_l4(state: dict, now: float) -> dict:
    """L3→L4: Co-occurrence clustering into L4 narrative summaries."""
    narrative_ids = await consolidate_l3_l4(db)
    if narrative_ids:
        return {"status": "promoted", "narratives": len(narrative_ids)}
    return {"status": "no_new_narratives"}


# ── v1.4: Verification during consolidation ────────────────────────────
# Based on Reconsolidation (Nader 2000): every recall is a verification opportunity.
# During consolidation, we also verify stale/never-verified memories.

async def _verify_stale() -> str | None:
    """Verify stale and never-verified memories during consolidation.

    Scans L2+ memories and updates verification_status based on change_speed
    and age since last verification. This is the dream-cycle equivalent of
    the brain's reconsolidation process.
    """
    await db.ensure_collection()

    # Administrative READ-ONLY internal scan (same rationale as
    # _admin_read_by_layer): 'layer'/'verification_status' are not
    # engine-filterable keys (ISO-11) and post-filtering is forbidden
    # (ISO-05). Predicates live INSIDE the SQL statement.
    rows = db._conn.execute(
        "SELECT id, payload FROM points "
        "WHERE collection=? "
        "AND json_extract(payload, '$.layer') IN (2, 3, 4) "
        "AND COALESCE(json_extract(payload, '$.verification_status'), 'never_verified') "
        "IN ('never_verified', 'stale') LIMIT ?",
        (db.collection, 50),
    ).fetchall()
    needs_check = _payloads(rows)

    if not needs_check:
        return None

    now_iso = datetime.now(UTC).isoformat()
    now_ts = datetime.now(UTC).timestamp()
    verified = 0
    stale = 0

    for mem in needs_check[:30]:  # Cap per batch
        payload = mem
        speed = payload.get("change_speed", "slow")
        current_status = payload.get("verification_status", "never_verified")

        # Determine new status based on change_speed and age
        new_status = "verified"
        source = "consolidation_check"

        if speed == "realtime":
            # Realtime facts are stale by definition during consolidation
            verified_at = payload.get("verified_at")
            if verified_at:
                try:
                    vts = datetime.fromisoformat(verified_at.replace("Z", "+00:00")).timestamp()
                    age_hours = (now_ts - vts) / 3600
                    new_status = "stale" if age_hours > 1 else "verified"
                except Exception:
                    new_status = "stale"
            else:
                new_status = "stale"
            source = "time_check"

        elif speed == "fast":
            # Fast-changing facts: stale if not verified in 48h
            verified_at = payload.get("verified_at")
            if verified_at:
                try:
                    vts = datetime.fromisoformat(verified_at.replace("Z", "+00:00")).timestamp()
                    age_hours = (now_ts - vts) / 3600
                    new_status = "stale" if age_hours > 48 else "verified"
                except Exception:
                    new_status = "verified"
            else:
                # Never verified fast fact — mark verified now, will be checked next cycle
                new_status = "verified"
            source = "time_check"

        elif speed == "never":
            new_status = "verified"
            source = "immutable"

        # slow: mark verified (file_check is v1.5 territory)
        # For now, slow facts get verified during consolidation
        new_status = "verified"
        source = "consolidation_check"

        # Update in the memory store (payload already carries its own scope)
        updated = {**payload,
            "verification_status": new_status,
            "verified_at": now_iso,
            "verification_source": source,
            "updated_at": now_iso,
        }
        mem_id = payload.get("memory_id", "")
        if mem_id:
            vector = payload.get("embedding")
            await db.upsert(mem_id, updated)
            if new_status == "stale":
                stale += 1
            else:
                verified += 1

    parts = []
    if verified:
        parts.append(f"{verified} verified")
    if stale:
        parts.append(f"{stale} marked stale")
    return f"Verification: {', '.join(parts)}" if parts else None


async def _run_consolidation_pass(state: dict, now: float) -> list[str]:
    results: list[str] = []
    for fn in [_promote_l1_l2, lambda s: _promote_l2_l3(s, now), lambda s: _promote_l3_l4(s, now), lambda s: _verify_stale()]:
        r = await fn(state)
        if isinstance(r, dict):
            if r.get("status") == "promoted":
                count = r.get("entities", r.get("narratives", 0))
                if count > 0:
                    results.append(f"Consolidation: {count} items promoted")
            continue
        if r:
            results.append(r)
    return results


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def heartbeat(agent_id: str = "default", turn_count: int = 1) -> HeartbeatResult:
    """Signal that the agent is alive. Triggers auto-consolidation if thresholds met."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + turn_count
    now = datetime.now(UTC).timestamp()
    results = await _run_consolidation_pass(state, now)
    if results:
        _save_state(state)
    return HeartbeatResult(status="ok", agent_id=agent_id, turn_count=state["turn_count"], message=", ".join(results) if results else "No consolidation due")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def consolidate(force: bool = False) -> ConsolidateResult:
    """Run consolidation across all layers."""
    state = _load_state()
    state["turn_count"] = state.get("turn_count", 0) + 1
    now = datetime.now(UTC).timestamp()
    if force:
        state["last_promote_l1_l2"] = 0
        state["last_promote_l2_l3"] = 0
        state["last_promote_l3_l4"] = 0
    results = await _run_consolidation_pass(state, now)
    _save_state(state)
    return ConsolidateResult(status="consolidation complete", forced=force, results=results)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def dream() -> dict:
    """Trigger a deep dream cycle — runs full L1->L4 consolidation pipeline."""
    state = _load_state()
    results = await run_consolidation(db, state, force=True)
    _save_state(state)
    if results:
        return {"status": "dream_complete", "results": results}
    return {"status": "no_new_consolidation"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dream_status(task_id: str) -> dict:
    """Check status of a background dream task."""
    from shared.task_queue import get_tracker
    info = get_tracker().get_status(task_id)
    if not info:
        return {"status": "not_found", "task_id": task_id}
    result: dict = {"status": info.status.value, "task_id": task_id}
    if info.result is not None:
        result["result"] = info.result if isinstance(info.result, dict) else {"value": str(info.result)}
    if info.error:
        result["error"] = info.error
    if info.duration_ms is not None:
        result["duration_ms"] = round(info.duration_ms, 0)
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def approve_promotion(point_ids: str, approved_by: str) -> dict:
    """M5-trunk (ISO-06/ISO-16): copy source points into the human-approved
    'merged' trunk with full provenance, and mark the sources merged_into.

    point_ids: JSON array string, e.g. '["id1","id2"]'. approved_by: human
    identity REQUIRED — automatic promotion never reaches the trunk.

    Returns {"merged_id", "approved_by", "sources": n}.
    """
    import hashlib as _hl
    import json as _json
    try:
        ids = _json.loads(point_ids)
    except _json.JSONDecodeError as e:
        return {"error": f"point_ids must be a JSON array: {e}"}
    if not isinstance(ids, list) or not ids:
        return {"error": "point_ids must be a non-empty JSON array"}
    if not isinstance(approved_by, str) or not approved_by.strip():
        return {"error": "approved_by is required (human identity)"}

    # M5-audit C1: solo se pueden aprobar fuentes que el llamador puede LEER
    # (scope propio + shared + merged). Un id privado ajeno = not_found.
    visible = {"must": [{"key": "agent_scope",
                         "match": {"any": [IDENTITY.agent_id, "shared", "merged"]}}]}
    sources = []
    for pid in ids:
        rec = await db.get(str(pid), filter=visible)
        if rec is None:
            return {"error": f"source point not found or not visible: {pid}"}
        sources.append(rec)

    new_id = "merged-" + _hl.sha256(",".join(sorted(map(str, ids))).encode()).hexdigest()[:16]
    if await db.get(new_id, filter=visible) is not None:
        return {"merged_id": new_id, "approved_by": approved_by, "sources": len(ids),
                "note": "already merged (idempotent)"}

    base_payload = dict(sources[0]["payload"])
    base_payload["content"] = "\n\n---\n\n".join(
        s["payload"].get("content", "") for s in sources
    )
    base_payload["agent_scope"] = "merged"
    base_payload["approved_by"] = approved_by.strip()
    base_payload["provenance"] = [
        {"from_scope": s["payload"].get("agent_scope", "shared"), "point_id": s["id"]}
        for s in sources
    ]
    base_payload["approved_at"] = datetime.now(UTC).isoformat()
    await db.upsert(new_id, base_payload, allow_reserved_scope=True)

    for s in sources:
        await db.update_payload(s["id"], {"merged_into": new_id})

    return {"merged_id": new_id, "approved_by": approved_by.strip(), "sources": len(ids)}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_consolidated(scope: str = "") -> LayerResult:
    """Get consolidated memories (L4)."""
    mems = _admin_read_by_layer(4, 20)
    return LayerResult(layer="L4_CONSOLIDATED", count=len(mems), memories=mems)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_semantic(scope: str = "") -> LayerResult:
    """Get semantic memories (L3)."""
    mems = _admin_read_by_layer(3, 20)
    return LayerResult(layer="L3_SEMANTIC", count=len(mems), memories=mems)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> ConsolidationStatusResult:
    """Show L0_to_L4_consolidation daemon status."""
    state = _load_state()
    return ConsolidationStatusResult(daemon="L0_to_L4_consolidation", status="RUNNING", state=state)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def force_promote(from_layer: int = 1, count: int = 10) -> dict:
    """Force promotion of memories between layers for testing."""
    await db.ensure_collection()
    if from_layer not in (1, 2, 3):
        return {"status": "error", "error": "from_layer must be 1, 2, or 3"}

    mems = _admin_read_by_layer(from_layer, count)
    if not mems:
        return {"status": "no_memories", "from_layer": from_layer, "message": f"No L{from_layer} memories found"}

    to_layer = from_layer + 1
    layer_map = {2: MemoryLayer.EPISODIC, 3: MemoryLayer.SEMANTIC, 4: MemoryLayer.CONSOLIDATED}
    promoted = 0
    for m in mems:
        new_item = MemoryItem(
            layer=layer_map[to_layer],
            scope_type=MemoryScope(m.get("scope_type", "agent")),
            scope_id=m.get("scope_id", "system"),
            type=MemoryType(m.get("type", "fact")),
            content=m.get("content", ""),
            importance=m.get("importance", 0.5),
            confidence=min(m.get("confidence", 0.5) + 0.1, 1.0),
        )
        payload = new_item.model_dump(mode="json")
        payload["agent_scope"] = m.get("agent_scope", "shared")  # promoted rows inherit source scope
        vector = None
        await db.upsert(new_item.memory_id, payload)
        promoted += 1

    return {"status": "promoted", "from_layer": f"L{from_layer}", "to_layer": f"L{to_layer}", "count": promoted}


def register_tools(target_mcp: FastMCP, target_qdrant, target_config: Config, prefix: str = "") -> None:
    """Register consolidation tools. Positional signature is a public contract.

    target_qdrant is IGNORED (M2-storage: SQLite MemoryDB replaced the Qdrant
    daemon); it stays in the signature for positional compatibility with the
    unified server.
    """
    global config, db
    config = target_config
    if db.embedding_dim != config.embedding_dim:
        db = MemoryDB(None, "L0_L4_memory", config.embedding_dim)
    for fn in [approve_promotion, heartbeat, consolidate, dream, dream_status, force_promote, get_consolidated, get_semantic, status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
