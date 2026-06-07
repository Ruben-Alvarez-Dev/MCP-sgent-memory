"""macOS Notification System — 4 reminders before cleanup expiry.

Sends macOS Notification Center alerts at:
  1. 30 days → "Entities marked for cleanup"
  2. 15 days → "Halfway to cleanup deadline"
  3. 7 days  → "One week until deletion"
  4. 1 day   → "LAST CHANCE — deletion tomorrow"

Each notification includes the entity name and days remaining.
Clicking "Keep" in the notification opens the governance dashboard.
"""
from __future__ import annotations

import os
import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional

from shared.env_loader import load_env
load_env()
from shared.config import Config
from shared.entity_registry import EntityRegistry
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager

logger = logging.getLogger(__name__)

config = Config.from_env()
data_dir = config.data_dir or os.path.join(config.server_dir, "data") if config.server_dir else "data"
db_path = os.path.join(data_dir, "entity_timeline.db")

registry = EntityRegistry(db_path)
CLEANUP_MARKER = "candidate_for_cleanup"
RETENTION_DAYS = 30

REMINDER_DAYS = [30, 15, 7, 1]
REMINDER_TITLES = {
    30: "🧠 Entities Marked for Cleanup",
    15: "⏳ Halfway to Cleanup Deadline",
    7:  "⚠️ One Week Until Deletion",
    1:  "🔥 LAST CHANCE — Deletion Tomorrow",
}

REMINDER_MESSAGES = {
    30: "has been marked for cleanup. You have 30 days to review it. Open the dashboard to Keep or Delete.",
    15: "will be deleted in 15 days if not reviewed. Open the governance dashboard.",
    7:  "will be permanently deleted in 7 days. Review now to prevent data loss.",
    1:  "will be DELETED TOMORROW. This is your final chance to Keep it.",
}


def send_notification(title: str, message: str, entity_name: str = "") -> bool:
    """Send macOS Notification Center alert."""
    try:
        full_message = f"{entity_name}: {message}" if entity_name else message
        cmd = [
            "osascript", "-e",
            f'display notification "{full_message}" with title "{title}"',
        ]
        subprocess.run(cmd, capture_output=True, timeout=5)
        logger.info("Notification sent: %s — %s", title, entity_name or "(general)")
        return True
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)
        return False


def get_cleanup_date(entity) -> Optional[datetime]:
    meta = entity.metadata or {}
    marked = meta.get("marked_for_cleanup_at")
    if not marked:
        return None
    try:
        return datetime.fromisoformat(marked)
    except (ValueError, TypeError):
        return None


def get_days_remaining(entity) -> Optional[int]:
    cd = get_cleanup_date(entity)
    if not cd:
        return None
    expiry = cd + timedelta(days=RETENTION_DAYS)
    remaining = (expiry - datetime.now(timezone.utc)).days
    return max(0, remaining)


def get_notification_stage(entity) -> Optional[int]:
    """Return which reminder stage applies (30, 15, 7, 1) or None."""
    remaining = get_days_remaining(entity)
    if remaining is None:
        return None

    meta = entity.metadata or {}
    sent_stages = meta.get("notification_stages_sent", [])

    for stage in REMINDER_DAYS:
        if remaining == stage and stage not in sent_stages:
            return stage

    return None


def mark_stage_sent(entity_id: str, stage: int):
    """Record that a notification stage was sent."""
    entity = registry.get(entity_id)
    if not entity:
        return
    meta = entity.metadata or {}
    sent = meta.get("notification_stages_sent", [])
    if stage not in sent:
        sent.append(stage)
    meta["notification_stages_sent"] = sent
    registry.update_metadata(entity_id, meta)


def check_and_notify(dry_run: bool = False) -> list[dict]:
    """Check all cleanup candidates and send pending notifications.

    Returns list of notifications sent.
    """
    candidates = registry.list_by_kind("concept", status=CLEANUP_MARKER)
    for k in ("agent", "project", "user", "system"):
        candidates += registry.list_by_kind(k, status=CLEANUP_MARKER)

    sent = []
    for entity in candidates:
        stage = get_notification_stage(entity)
        if stage is None:
            continue

        title = REMINDER_TITLES.get(stage, "Memory Cleanup Reminder")
        msg = REMINDER_MESSAGES.get(stage, "Entity pending cleanup review.")

        if dry_run:
            logger.info("[DRY RUN] Would notify: %s → %s days remaining", entity.name, stage)
            sent.append({"entity_id": entity.entity_id, "name": entity.name, "stage": stage, "title": title})
            continue

        ok = send_notification(title, msg, entity.name)
        if ok:
            mark_stage_sent(entity.entity_id, stage)
            sent.append({"entity_id": entity.entity_id, "name": entity.name, "stage": stage, "title": title})

        # Purge expired entities (expired + all stages sent)
        remaining = get_days_remaining(entity)
        if remaining == 0:
            from shared.relation_manager import RelationManager
            from shared.entity_timeline import EntityTimeline
            rel_manager = RelationManager(db_path)
            tl = EntityTimeline(db_path)
            rel_manager.delete_entity_relations(entity.entity_id)
            tl.delete_entity_events(entity.entity_id)
            registry.update_status(entity.entity_id, "archived")
            registry.update_summary(entity.entity_id,
                                    f"[AUTO-ARCHIVED {datetime.now(timezone.utc).isoformat()}]")
            logger.info("Auto-archived expired entity: %s (%s)", entity.name, entity.entity_id)

    return sent


def notify_all(dry_run: bool = False) -> dict:
    """Main entry point. Check all candidates and return results."""
    sent = check_and_notify(dry_run)
    total_candidates = len(registry.list_by_kind("concept", status=CLEANUP_MARKER))
    for k in ("agent", "project", "user", "system"):
        total_candidates += len(registry.list_by_kind(k, status=CLEANUP_MARKER))
    return {
        "notifications_sent": len(sent),
        "total_candidates": total_candidates,
        "dry_run": dry_run,
        "notifications": sent[:20],
    }


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    result = notify_all(dry)
    print(json.dumps(result, indent=2, default=str))
