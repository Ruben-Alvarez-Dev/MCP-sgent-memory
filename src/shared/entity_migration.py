"""Entity Migration — backfill existing raw events into entity timelines.

Migrates raw_events.jsonl into entity timelines by:
1. Reading all existing raw events
2. Grouping by actor_id → each actor becomes an entity
3. Detecting project/document/concept entities from event content
4. Creating contact points when entities interact
5. Preserving all original event data

Safe to run multiple times (idempotent via event_id dedup).
"""
from __future__ import annotations

import json
import logging
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.entity_registry import EntityRegistry
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager

logger = logging.getLogger(__name__)

PROJECT_PATTERNS = re.compile(
    r"(?:project|repo|repository)\s*[:=]\s*[\"']?([\w./-]+)",
    re.IGNORECASE,
)


def _is_sane_candidate(name: str) -> bool:
    """Minimum sanity for a regex-detected entity candidate.

    Rejects the junk classes documented in repair plan finding D4:
    short fragments (\"A\", \"---\"), URL pieces (\"https\") and
    filesystem paths (\"/Users/...\", \".worktrees/...\").
    """
    if len(name) < 3:
        return False
    if not re.search(r"[A-Za-z]", name):
        return False
    lowered = name.lower()
    if lowered.startswith(("http", "www.")) or "://" in lowered:
        return False
    if name.startswith(("/", "./", "~", "..", ".")) or "/users/" in lowered:
        return False
    return True


def _resolve_known_entity(registry: EntityRegistry, name: str):
    """Return the registry entity matching `name` (exact, then
    case-insensitive), or None. Catalog-validated linking only —
    this function never creates entities (repair plan P2)."""
    entity = registry.get_by_name(name)
    if entity is None:
        entity = registry.get_by_name_ci(name)
    return entity


def migrate_raw_events(
    jsonl_path: str,
    registry: EntityRegistry,
    timeline: EntityTimeline,
    relations: RelationManager,
    dry_run: bool = True,
) -> dict:
    """Backfill raw_events.jsonl into entity timelines.

    Args:
        jsonl_path: Path to raw_events.jsonl
        registry: EntityRegistry instance
        timeline: EntityTimeline instance
        relations: RelationManager instance
        dry_run: If True, only count — don't write

    Returns:
        dict with counts: total_events, entities_created, events_appended, relations_created
    """
    path = Path(jsonl_path)
    if not path.exists():
        return {"error": f"File not found: {jsonl_path}"}

    raw_events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    raw_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not raw_events:
        return {"total_events": 0, "message": "No events to migrate"}

    logger.info("Migrating %d raw events into entity timelines...", len(raw_events))

    actor_entities = {}  # actor_id → entity_id
    project_entities = {}  # project_name → entity_id
    total_appended = 0
    total_relations = 0
    total_entities = 0

    for ev in raw_events:
        event_id = ev.get("event_id", "")
        if not event_id:
            continue

        actor_id = ev.get("actor_id", "system") or "system"
        session_id = ev.get("session_id", "")
        event_type = ev.get("type", "system")
        timestamp = ev.get("timestamp", "")
        attributes = ev.get("attributes", {}) or {}
        content = attributes.get("content", "")

        # Skip if already processed (check by source_event_id)
        existing = timeline.search("system", event_id, limit=1)
        if existing:
            continue

        # 1. Ensure actor entity exists
        if actor_id not in actor_entities:
            if not dry_run:
                try:
                    entity = registry.register(
                        name=actor_id,
                        kind="agent" if actor_id != "system" else "system",
                        summary=f"Actor in the multi-agent system",
                    )
                    actor_entities[actor_id] = entity.entity_id
                    total_entities += 1
                except ValueError:
                    entity = registry.get_by_name(actor_id)
                    if entity:
                        actor_entities[actor_id] = entity.entity_id
            else:
                actor_entities[actor_id] = f"dry-{actor_id}"
                total_entities += 1

        # 2. Append event to actor's timeline
        if not dry_run:
            result = timeline.append(
                entity_id=actor_entities[actor_id],
                event_type=event_type,
                content=content[:500] if content else event_type,
                metadata={
                    "session_id": session_id,
                    "event_id": event_id,
                    "source": ev.get("source", ""),
                    "scope": ev.get("scope", ""),
                },
                source_event_id=event_id,
            )
            total_appended += 1

            # Mark milestone on first event
            if total_appended == 1:
                timeline.append_milestone(
                    entity_id=actor_entities[actor_id],
                    milestone="created",
                    event_id=result["id"],
                    description="First event captured",
                )

            # 3. Detect project references in content → link to KNOWN
            #    entities only. Unknown candidates are quarantined in
            #    entity_candidates, never auto-registered (repair plan P2).
            if content:
                projects = PROJECT_PATTERNS.findall(content)
                for proj in projects:
                    if proj not in project_entities:
                        if not _is_sane_candidate(proj):
                            continue
                        proj_entity = _resolve_known_entity(registry, proj)
                        if proj_entity:
                            project_entities[proj] = proj_entity.entity_id
                        else:
                            registry.add_candidate(proj, sample_content=content[:300])
                            continue

                    if proj in project_entities:
                        proj_event = timeline.append(
                            entity_id=project_entities[proj],
                            event_type="reference",
                            content=f"Referenced by {actor_id}: {content[:200]}",
                            source_event_id=event_id,
                        )
                        relations.connect_symmetric(
                            entity_a=actor_entities[actor_id],
                            entity_b=project_entities[proj],
                            relation_type="reference",
                            event_a=result["id"],
                            event_b=proj_event["id"],
                            label_a=f"mentioned {proj}",
                            label_b=f"referenced by {actor_id}",
                        )
                        total_relations += 1

        else:
            total_appended += 1
            if content:
                projects = [p for p in PROJECT_PATTERNS.findall(content)
                            if _is_sane_candidate(p)]
                total_relations += len(projects) * 2

    result = {
        "total_events": len(raw_events),
        "entities_created": total_entities,
        "events_appended": total_appended,
        "relations_created": total_relations,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info(
            "DRY RUN: Would migrate %d events → ~%d entities, "
            "%d events, %d relations",
            len(raw_events), total_entities,
            total_appended, total_relations,
        )
    else:
        logger.info(
            "Migration complete: %d events → %d entities, "
            "%d timeline events, %d relations",
            len(raw_events), total_entities,
            total_appended, total_relations,
        )

    return result
