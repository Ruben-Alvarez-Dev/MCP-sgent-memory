"""Vault Entity Bridge — render entity timelines as markdown.

Syncs entity data to the vault/Entidades/ directory for human reading.
Each entity gets its own markdown file with timeline, relations, and milestones.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.entity_registry import EntityRegistry, EntityNode
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager

logger = logging.getLogger(__name__)


class VaultEntityBridge:
    """Syncs entity data to vault markdown files."""

    def __init__(self, vault_path: str,
                 registry: EntityRegistry,
                 timeline: EntityTimeline,
                 relations: RelationManager):
        self._vault = Path(vault_path) / "Entidades"
        self._reg = registry
        self._tl = timeline
        self._rel = relations
        self._vault.mkdir(parents=True, exist_ok=True)

    def to_markdown(self, entity_id: str) -> Optional[str]:
        """Render an entity's full state as markdown."""
        entity = self._reg.get(entity_id)
        if not entity:
            return None

        lines = []
        lines.append(f"# {entity.name}")
        lines.append(f"\n**ID:** {entity.entity_id}")
        lines.append(f"**Kind:** {entity.kind}")
        lines.append(f"**Status:** {entity.status}")
        lines.append(f"**Created:** {entity.created_at}")
        lines.append(f"**Updated:** {entity.updated_at}")
        if entity.summary:
            lines.append(f"\n{entity.summary}")

        # Timeline (chronological, last 20)
        events = self._tl.query_chronological(entity_id, limit=20)
        if events:
            lines.append(f"\n## Timeline ({len(events)} events)")
            for e in events:
                ts = e["timestamp"][:19] if e["timestamp"] else "?"
                meta = json.loads(e["metadata"]) if isinstance(e["metadata"], str) else e["metadata"] or {}
                meta_str = f" — {json.dumps(meta)}" if meta else ""
                lines.append(f"- [{ts}] **{e['event_type']}**: {e['content'][:200]}{meta_str}")

        # Milestones
        epochs = self._tl.get_epochs(entity_id)
        if epochs:
            lines.append(f"\n## Milestones ({len(epochs)})")
            for ep in epochs:
                lines.append(f"- **{ep['milestone']}** ({ep['timestamp'][:19]}): {ep['description']}")

        # Relations
        edges = self._rel.get_relations(entity_id)
        if edges:
            lines.append(f"\n## Relations ({len(edges)})")
            for edge in edges:
                other = edge.target_id if edge.source_id == entity_id else edge.source_id
                direction = "→" if edge.source_id == entity_id else "←"
                other_entity = self._reg.get(other)
                other_name = other_entity.name if other_entity else other[:12]
                lines.append(f"- {direction} **{other_name}** ({edge.relation_type})"
                             f" — events {edge.source_event_id}→{edge.target_event_id}"
                             f"{' — ' + edge.label if edge.label else ''}")

        return "\n".join(lines)

    def to_graphviz(self, entity_ids: list[str]) -> str:
        """Render entity graph as DOT for visualization."""
        lines = ['digraph EntityGraph {']
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=box, style=rounded];')

        seen = set(entity_ids)
        for eid in entity_ids:
            entity = self._reg.get(eid)
            label = entity.name if entity else eid[:12]
            lines.append(f'  "{eid}" [label="{label}"];')
            edges = self._rel.get_relations(eid)
            for edge in edges:
                other = edge.target_id if edge.source_id == eid else edge.source_id
                ab = f'  "{eid}" -> "{other}"'
                if ab not in seen:
                    seen.add(ab)
                    lines.append(f'  {ab} [label="{edge.relation_type}"];')

        lines.append('}')
        return "\n".join(lines)

    def sync_to_vault(self, entity_id: str) -> Optional[Path]:
        """Write entity markdown to vault/Entidades/."""
        md = self.to_markdown(entity_id)
        if not md:
            return None
        entity = self._reg.get(entity_id)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in entity.name)
        filepath = self._vault / f"{safe_name}.md"
        filepath.write_text(md)
        logger.info("Synced entity %s to vault: %s", entity_id, filepath)
        return filepath

    def sync_all(self) -> int:
        """Sync all active entities to vault. Returns count synced."""
        entities = self._reg.list_by_kind("project", status="active")
        entities += self._reg.list_by_kind("user", status="active")
        entities += self._reg.list_by_kind("agent", status="active")
        entities += self._reg.list_by_kind("system", status="active")
        seen = {e.entity_id for e in entities}
        for e in entities:
            self.sync_to_vault(e.entity_id)
        return len(seen)
