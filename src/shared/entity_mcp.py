"""Entity MCP server — expose entity timeline operations as tools.

Registers MCP tools for:
- Entity CRUD (register, get, search, update status)
- Timeline operations (append, query, get epochs, get surrounding)
- Relation operations (connect, traverse, get contact point)
- Vault sync (to_markdown, sync_to_vault)
- Migration (backfill raw events)
"""
from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from shared.env_loader import load_env
load_env()
from shared.config import Config
from shared.entity_registry import EntityRegistry, VALID_STATUSES
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager, VALID_RELATION_TYPES
from shared.vault_entity_bridge import VaultEntityBridge
from shared.entity_migration import migrate_raw_events

logger = logging.getLogger(__name__)

config = Config.from_env()
data_dir = config.data_dir or os.path.join(config.server_dir, "data") if config.server_dir else "data"
os.makedirs(data_dir, exist_ok=True)

# Shared instances
db_path = os.path.join(data_dir, "entity_timeline.db")
registry = EntityRegistry(db_path)
timeline = EntityTimeline(db_path)
relations = RelationManager(db_path)
vault_bridge = VaultEntityBridge(
    vault_path=os.path.join(config.server_dir, "data", "vault") if config.server_dir else "data/vault",
    registry=registry,
    timeline=timeline,
    relations=relations,
)

mcp = FastMCP("entity_server")


# ── Entity CRUD ─────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_register(name: str, kind: str = "concept",
                          metadata: str = "", summary: str = "") -> dict:
    """Register a new entity."""
    meta = json.loads(metadata) if metadata else {}
    entity = registry.register(name, kind, meta, summary)
    return entity.to_dict()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_get(entity_id: str) -> dict:
    """Get an entity by ID."""
    entity = registry.get(entity_id)
    return entity.to_dict() if entity else {"error": "Entity not found"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_get_by_name(name: str) -> dict:
    """Get an entity by name."""
    entity = registry.get_by_name(name)
    return entity.to_dict() if entity else {"error": f"Entity '{name}' not found"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_search(query: str, limit: int = 20) -> list[dict]:
    """Search entities by name or summary."""
    return [e.to_dict() for e in registry.search(query, limit)]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_list(kind: str = "", status: str = "", limit: int = 50) -> list[dict]:
    """List entities, optionally filtered by kind and/or status."""
    if kind:
        results = registry.list_by_kind(kind, status if status else None)
    else:
        results = registry.list_recent(limit)
    if status and not kind:
        results = [e for e in results if e.status == status]
    return [e.to_dict() for e in results[:limit]]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_update_status(entity_id: str, status: str) -> dict:
    """Update entity lifecycle status (active, dormant, archived, dead)."""
    ok = registry.update_status(entity_id, status)
    return {"success": ok, "entity_id": entity_id, "new_status": status if ok else "unchanged"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_update_summary(entity_id: str, summary: str) -> dict:
    """Update an entity's summary."""
    ok = registry.update_summary(entity_id, summary)
    return {"success": ok, "entity_id": entity_id}


# ── Timeline Operations ──────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_timeline_append(entity_id: str, event_type: str,
                                 content: str = "", metadata: str = "",
                                 source_event_id: str = "") -> dict:
    """Append an event to an entity's timeline."""
    meta = json.loads(metadata) if metadata else {}
    result = timeline.append(entity_id, event_type, content, meta, source_event_id)
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_timeline_query(entity_id: str, event_type: str = "",
                                from_ts: str = "", to_ts: str = "",
                                limit: int = 50, chronological: bool = False) -> list[dict]:
    """Query events from an entity's timeline."""
    kwargs = {"limit": limit}
    if event_type:
        kwargs["event_type"] = event_type
    if from_ts:
        kwargs["from_ts"] = from_ts
    if to_ts:
        kwargs["to_ts"] = to_ts

    if chronological:
        kwargs.pop("offset", None)
        return timeline.query_chronological(entity_id, **kwargs)
    return timeline.query(entity_id, **kwargs)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_timeline_epochs(entity_id: str) -> list[dict]:
    """Get timeline milestones/epochs for an entity."""
    return timeline.get_epochs(entity_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_timeline_surrounding(entity_id: str, event_id: int,
                                      window: int = 5) -> list[dict]:
    """Get events before and after a specific event."""
    return timeline.get_surrounding(entity_id, event_id, window)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_timeline_search(entity_id: str, query: str,
                                 limit: int = 20) -> list[dict]:
    """Search within an entity's timeline."""
    return timeline.search(entity_id, query, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_timeline_milestone(entity_id: str, milestone: str,
                                    event_id: int, description: str = "") -> dict:
    """Mark a lifecycle milestone for an entity, anchored to a specific event."""
    ok = timeline.append_milestone(entity_id, milestone, event_id, description)
    return {"success": ok, "entity_id": entity_id, "milestone": milestone}


# ── Relation Operations ──────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_relation_connect(source_id: str, target_id: str,
                                  relation_type: str,
                                  source_event_id: int, target_event_id: int,
                                  label: str = "") -> dict:
    """Create a bidirectional relation between two entities."""
    edge = relations.connect(source_id, target_id, relation_type,
                             source_event_id, target_event_id, label=label)
    return edge.to_dict()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_relation_get(entity_id: str) -> list[dict]:
    """Get all relations involving an entity."""
    return [e.to_dict() for e in relations.get_relations(entity_id)]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_relation_contact(entity_a: str, entity_b: str) -> dict:
    """Get the contact point (relations) between two entities."""
    cp = relations.get_contact_point(entity_a, entity_b)
    if cp:
        return {"edges": [e.to_dict() for e in cp]}
    return {"edges": [], "message": "No direct relation between these entities"}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_relation_traverse(entity_id: str, relation_type: str = "",
                                   max_depth: int = 2) -> list[dict]:
    """BFS traversal from entity through relations."""
    kwargs = {"max_depth": max_depth}
    if relation_type:
        kwargs["relation_type"] = relation_type
    return relations.traverse(entity_id, **kwargs)


# ── Vault Sync ────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_to_markdown(entity_id: str) -> str:
    """Render an entity's timeline + relations as markdown."""
    result = vault_bridge.to_markdown(entity_id)
    return result or "Entity not found"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_sync_to_vault(entity_id: str) -> dict:
    """Write entity markdown to vault/Entidades/."""
    path = vault_bridge.sync_to_vault(entity_id)
    return {"synced": bool(path), "path": str(path) if path else ""}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_sync_all() -> dict:
    """Sync all active entities to vault markdown."""
    count = vault_bridge.sync_all()
    return {"synced": count}


# ── Migration ────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
async def entity_migrate(dry_run: bool = True) -> dict:
    """Backfill existing raw_events.jsonl into entity timelines."""
    jsonl_path = config.L0_events_jsonl or config.data_dir and os.path.join(
        config.data_dir, "L0-sensory", "events.jsonl"
    )
    if not jsonl_path or not os.path.exists(jsonl_path):
        return {"error": f"Raw events file not found: {jsonl_path}"}
    return migrate_raw_events(jsonl_path, registry, timeline, relations, dry_run)


# ── Server Info ──────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def entity_server_status() -> dict:
    """Get entity server status."""
    return {
        "entity_count": registry.count(),
        "timeline_entities": timeline.count_entities(),
        "timeline_events": sum(timeline.count_events(e.entity_id) for e in registry.list_recent(999)) if registry.count() > 0 else 0,
        "relation_count": relations.count(),
        "vault_path": str(vault_bridge._vault),
    }


def main():
    """Run entity MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
