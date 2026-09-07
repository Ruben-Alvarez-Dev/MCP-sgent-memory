"""Lexical consolidation pipeline (M6: MEM-01, MEM-02, MEM-03).

Replaces the ISO-06 NO-OPs with actual lexical consolidation:
  - L1->L2: Group working memories into episodes by scope+time
  - L2->L3: Extract entities from episodes into semantic points
  - L3->L4: Co-occurrence clustering into narrative summaries

All consolidation is deterministic — no LLM, no embeddings.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict

from .entity import extract_entities
from .memory_db import MemoryDB
from .models import MemoryItem, MemoryLayer, MemoryScope, MemoryType

logger = logging.getLogger(__name__)


async def consolidate_l1_l2(
    db: MemoryDB,
    min_events: int = 2,
    max_events: int = 10,
) -> list[str]:
    """Group L1 working memories into L2 episodes by (scope_type, scope_id).

    Groups with >= min_events events become an L2 episode point.
    Idempotent: running twice produces identical results (checked by scope_id).

    Returns: list of created episode IDs.
    """
    rows = db._conn.execute(
        "SELECT id, payload FROM points "
        "WHERE collection=? AND json_extract(payload, '$.layer')=1",
        (db.collection,),
    ).fetchall()

    if len(rows) < min_events:
        return []

    groups: dict[str, list[dict]] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        scope_type = payload.get("scope_type", "agent")
        scope_id = payload.get("scope_id", "system")
        key = f"{scope_type}/{scope_id}"
        groups.setdefault(key, []).append(payload)

    episode_ids = []
    for key, items in groups.items():
        if len(items) < min_events:
            continue
        scope_type, scope_id = key.split("/", 1)
        content_lines = [f"- {m.get('content', '')[:200]}" for m in items[:max_events]]
        content = f"Episode ({len(items)} events):\n" + "\n".join(content_lines)
        avg_importance = sum(m.get("importance", 0.3) for m in items) / len(items)

        try:
            scope_enum = MemoryScope(scope_type)
        except ValueError:
            scope_enum = MemoryScope.AGENT

        episode = MemoryItem(
            layer=MemoryLayer.EPISODIC,
            scope_type=scope_enum,
            scope_id=scope_id,
            type=MemoryType.EPISODE,
            content=content,
            importance=avg_importance,
            confidence=0.7,
        )
        payload = episode.model_dump(mode="json")
        source_scope = items[0].get("agent_scope", "shared")
        payload["agent_scope"] = source_scope
        payload["source_ids"] = [m.get("id") for m in items]

        ep_id = f"ep-{hashlib.sha256(key.encode()).hexdigest()[:12]}"
        await db.upsert(ep_id, None, payload)
        episode_ids.append(ep_id)

    return episode_ids


async def consolidate_l2_l3(db: MemoryDB) -> list[str]:
    """Extract entities from L2 episodes into L3 semantic points.

    For each L2 episode, extracts CamelCase/UPPER_SNAKE entities and creates
    L3 points with type=entity. Updates the entities table (mention_count).
    Idempotent: existing entities get mention_count incremented.

    Returns: list of created L3 point IDs.
    """
    rows = db._conn.execute(
        "SELECT id, payload FROM points "
        "WHERE collection=? AND json_extract(payload, '$.layer')=2",
        (db.collection,),
    ).fetchall()

    if not rows:
        return []

    l3_ids = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue

        content = payload.get("content", "")
        entities = extract_entities(content)
        scope = payload.get("agent_scope", "shared")
        scope_type = payload.get("scope_type", "agent")
        scope_id = payload.get("scope_id", "system")

        for entity in entities:
            try:
                scope_enum = MemoryScope(scope_type)
            except ValueError:
                scope_enum = MemoryScope.AGENT

            entity_item = MemoryItem(
                layer=MemoryLayer.SEMANTIC,
                scope_type=scope_enum,
                scope_id=scope_id,
                type=MemoryType.ENTITY,
                content=f"Entity: {entity['name']} ({entity['type']})",
                importance=0.8,
                confidence=0.9,
            )
            entity_payload = entity_item.model_dump(mode="json")
            entity_payload["agent_scope"] = scope
            entity_payload["entity_name"] = entity["name"]
            entity_payload["entity_type"] = entity["type"]
            entity_payload["source_episode_id"] = row["id"]

            ent_key = f"{scope}:{entity['name']}"
            ent_id = f"ent-{hashlib.sha256(ent_key.encode()).hexdigest()[:12]}"
            await db.upsert(ent_id, None, entity_payload)
            l3_ids.append(ent_id)

            db._upsert_entity(entity["name"], entity["type"], scope, 3)

    return l3_ids


async def consolidate_l3_l4(db: MemoryDB, min_cooccurrence: int = 3) -> list[str]:
    """Create L4 narrative summaries from co-occurring L3 entities.

    Finds entity pairs that appear together in >= min_cooccurrence L3 points
    and creates L4 narrative points + relations.

    Returns: list of created L4 point IDs.
    """
    rows = db._conn.execute(
        "SELECT id, payload FROM points "
        "WHERE collection=? AND json_extract(payload, '$.layer')=3 "
        "AND json_extract(payload, '$.type')='entity'",
        (db.collection,),
    ).fetchall()

    if len(rows) < min_cooccurrence:
        return []

    episode_entities: dict[str, list[str]] = defaultdict(list)
    entity_scopes: dict[str, str] = {}

    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        entity_name = payload.get("entity_name", "")
        episode_id = payload.get("source_episode_id", "")
        scope = payload.get("agent_scope", "shared")
        if entity_name and episode_id:
            episode_entities[episode_id].append(entity_name)
            entity_scopes[entity_name] = scope

    cooccurrence: Counter = Counter()
    for entities in episode_entities.values():
        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1:]:
                pair = tuple(sorted([e1, e2]))
                cooccurrence[pair] += 1

    l4_ids = []
    for (e1, e2), count in cooccurrence.items():
        if count < min_cooccurrence:
            continue
        scope = entity_scopes.get(e1, "shared")

        narrative = MemoryItem(
            layer=MemoryLayer.CONSOLIDATED,
            scope_type=MemoryScope.AGENT,
            scope_id=scope,
            type=MemoryType.NARRATIVE,
            content=f"Pattern: {e1} and {e2} co-occur in {count} episodes",
            importance=0.6,
            confidence=0.7,
        )
        narrative_payload = narrative.model_dump(mode="json")
        narrative_payload["agent_scope"] = scope
        narrative_payload["pattern_entities"] = [e1, e2]
        narrative_payload["cooccurrence_count"] = count

        narr_key = f"{e1}:{e2}"
        narr_id = f"narr-{hashlib.sha256(narr_key.encode()).hexdigest()[:12]}"
        await db.upsert(narr_id, None, narrative_payload)
        l4_ids.append(narr_id)

        db._upsert_relation(e1, e2, "uses", scope, strength=min(1.0, count / 10.0))

    return l4_ids


async def run_consolidation(
    db: MemoryDB,
    state: dict,
    force: bool = False,
) -> list[str]:
    """Run the full consolidation pipeline: L1->L2->L3->L4.

    Each stage runs only if enough new data exists since last run.
    Returns list of status messages.
    """
    results = []

    # L1->L2: Episode creation
    l1_count = state.get("last_promote_l1_l2", 0)
    turn_threshold = 10
    if force or state.get("turn_count", 0) - l1_count >= turn_threshold:
        episode_ids = await consolidate_l1_l2(db)
        if episode_ids:
            results.append(f"L1->L2: {len(episode_ids)} episodes created")
        state["last_promote_l1_l2"] = state.get("turn_count", 0)

    # L2->L3: Entity extraction
    l2_count = state.get("last_promote_l2_l3", 0)
    if force or state.get("last_promote_l1_l2", 0) != l2_count:
        entity_ids = await consolidate_l2_l3(db)
        if entity_ids:
            results.append(f"L2->L3: {len(entity_ids)} entities extracted")
        state["last_promote_l2_l3"] = state.get("turn_count", 0)

    # L3->L4: Co-occurrence clustering
    l3_count = state.get("last_promote_l3_l4", 0)
    if force or state.get("last_promote_l2_l3", 0) != l3_count:
        narrative_ids = await consolidate_l3_l4(db)
        if narrative_ids:
            results.append(f"L3->L4: {len(narrative_ids)} narratives created")
        state["last_promote_l3_l4"] = state.get("turn_count", 0)

    return results
