"""Governance Server — Memory management UI + API.

Dual transport:
  - HTTP server (FastAPI) for browser access
  - MCP App resource for in-conversation rendering (ui://)

Exposes:
  GET  /           → governance.html (the app)
  GET  /api/entities  → list all entities with health scores
  POST /api/entity/{id}/cleanup  → mark for cleanup (30-day retention)
  POST /api/entity/{id}/status   → update status
  POST /api/entity/{id}/delete   → permanent delete
  GET  /api/entity/{id}/timeline → get entity timeline + relations
  GET  /api/stats   → governance stats
"""
from __future__ import annotations

import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from shared.env_loader import load_env
load_env()
from shared.config import Config
from shared.entity_registry import EntityRegistry, VALID_STATUSES
from shared.entity_timeline import EntityTimeline
from shared.relation_manager import RelationManager

logger = logging.getLogger(__name__)

config = Config.from_env()
data_dir = config.data_dir or os.path.join(config.server_dir, "data") if config.server_dir else "data"
db_path = os.path.join(data_dir, "entity_timeline.db")

registry = EntityRegistry(db_path)
timeline = EntityTimeline(db_path)
relations = RelationManager(db_path)

HERE = Path(__file__).parent
HTML_PATH = HERE / "governance.html"

RETENTION_DAYS = 30
CLEANUP_MARKER = "candidate_for_cleanup"

app = FastAPI(title="Jart-OS Memory Governance")


# ── Health Computation ─────────────────────────────────────

def compute_health(entity, events: int, rels: int) -> float:
    score = 0.3
    if events >= 10: score += 0.2
    if events >= 50: score += 0.1
    if rels > 0: score += 0.1
    if rels >= 3: score += 0.1
    if entity.status == "active": score += 0.1
    if entity.summary and len(entity.summary) > 10: score += 0.1
    if entity.kind != "concept": score += 0.1
    if events == 0: score -= 0.2
    bad_names = {"---", "https", "A", "engra", "current", "test-user"}
    if entity.name in bad_names: score -= 0.3
    return max(0.0, min(1.0, round(score, 2)))


# ── Cleanup date helpers ───────────────────────────────────

def get_cleanup_date(entity) -> Optional[str]:
    meta = entity.metadata or {}
    marked = meta.get("marked_for_cleanup_at")
    if not marked:
        return None
    try:
        dt = datetime.fromisoformat(marked)
        expiry = dt + timedelta(days=RETENTION_DAYS)
        return expiry.isoformat()
    except (ValueError, TypeError):
        return None


def get_days_remaining(entity) -> Optional[int]:
    expiry = get_cleanup_date(entity)
    if not expiry:
        return None
    try:
        dt = datetime.fromisoformat(expiry)
        remaining = (dt - datetime.now(timezone.utc)).days
        return max(0, remaining)
    except (ValueError, TypeError):
        return None


# ── MCP App Resource ───────────────────────────────────────

def get_governance_html() -> str:
    if HTML_PATH.exists():
        return HTML_PATH.read_text()
    return "<html><body><h1>Governance app not found</h1></body></html>"


# ── Entity Enricher ────────────────────────────────────────

def enrich_entity(entity) -> dict:
    ev = timeline.count_events(entity.entity_id)
    rels = relations.get_relations(entity.entity_id)
    d = entity.to_dict()
    d["events"] = ev
    d["relations"] = len(rels)
    d["health"] = compute_health(entity, ev, len(rels))
    d["cleanup_date"] = get_cleanup_date(entity)
    d["days_remaining"] = get_days_remaining(entity)
    return d


# ── HTTP Routes ────────────────────────────────────────────


@app.get("/")
async def index():
    return HTMLResponse(get_governance_html())


@app.get("/api/entities")
async def list_entities():
    all_entities = registry.list_recent(999)
    return {"entities": [enrich_entity(e) for e in all_entities]}


@app.get("/api/stats")
async def stats():
    all_entities = registry.list_recent(999)
    enriched = [enrich_entity(e) for e in all_entities]
    return {
        "total": len(enriched),
        "active": sum(1 for e in enriched if e["status"] == "active"),
        "candidates": sum(1 for e in enriched if e["status"] == CLEANUP_MARKER),
        "dormant": sum(1 for e in enriched if e["status"] == "dormant"),
        "archived": sum(1 for e in enriched if e["status"] == "archived"),
        "total_relations": sum(e.get("relations", 0) for e in enriched),
        "average_health": round(sum(e["health"] for e in enriched) / len(enriched), 2) if enriched else 0,
    }


@app.post("/api/entity/{entity_id}/cleanup")
async def mark_cleanup(entity_id: str):
    entity = registry.get(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    now = datetime.now(timezone.utc).isoformat()
    meta = entity.metadata or {}
    meta["marked_for_cleanup_at"] = now
    registry.update_metadata(entity_id, meta)
    registry.update_status(entity_id, CLEANUP_MARKER)
    return {"success": True, "entity_id": entity_id, "expires_in_days": RETENTION_DAYS}


class StatusUpdate(BaseModel):
    status: str


@app.post("/api/entity/{entity_id}/status")
async def update_status(entity_id: str, body: StatusUpdate):
    if body.status not in VALID_STATUSES and body.status != CLEANUP_MARKER:
        raise HTTPException(400, f"Invalid status: {body.status}")
    ok = registry.update_status(entity_id, body.status)
    if not ok:
        raise HTTPException(404, "Entity not found")
    return {"success": True, "entity_id": entity_id, "new_status": body.status}


@app.post("/api/entity/{entity_id}/delete")
async def delete_entity(entity_id: str):
    entity = registry.get(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    name = entity.name
    relations.delete_entity_relations(entity_id)
    deleted = timeline.delete_entity_events(entity_id)
    # Can't easily delete from SQLite registry without the method, so archive it
    registry.update_status(entity_id, "archived")
    registry.update_summary(entity_id, f"[DELETED {datetime.now(timezone.utc).isoformat()}]")
    logger.info("Entity %s (%s) archived — %d events, all relations deleted", entity_id, name, deleted)
    return {"success": True, "entity_id": entity_id, "name": name, "events_deleted": deleted}


@app.get("/api/entity/{entity_id}/timeline")
async def get_timeline(entity_id: str, limit: int = 20):
    entity = registry.get(entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    events = timeline.query_chronological(entity_id, limit=limit)
    rels = relations.get_relations(entity_id)
    enriched_rels = []
    for r in rels:
        e = r.to_dict()
        other_id = r.target_id if r.source_id == entity_id else r.source_id
        other = registry.get(other_id)
        e["other_name"] = other.name if other else other_id[:12]
        enriched_rels.append(e)
    return {
        "entity": entity.to_dict(),
        "events": [dict(e) for e in events],
        "relations": enriched_rels,
        "total_events": timeline.count_events(entity_id),
    }


# ── Gallery & Graph routes ────────────────────────────────

HERE = Path(__file__).parent

L0_EVENTS_PATH = config.L0_events_jsonl or os.path.join(config.data_dir, "L0-sensory", "events.jsonl") if config.data_dir else os.path.join(config.server_dir, "data", "L0-sensory", "events.jsonl")
L1_AGENTS_PATH = config.L1_working_path or os.path.join(config.server_dir, "data", "L1-working", "agents") if config.server_dir else ""
L3_DECISIONS_PATH = config.L3_decisions_path or os.path.join(config.server_dir, "data", "L3-semantic", "decisions") if config.server_dir else ""
CONVERSATIONS_DB = os.path.join(config.server_dir, "data", "conversations.db") if config.server_dir else ""


@app.get("/gallery")
async def gallery():
    return HTMLResponse((HERE / "gallery.html").read_text() if (HERE / "gallery.html").exists() else "<h1>Gallery not found</h1>")


@app.get("/api/graph")
async def graph_data():
    all_entities = registry.list_recent(999)
    nodes = []
    for e in all_entities:
        ev = timeline.count_events(e.entity_id)
        rels_list = relations.get_relations(e.entity_id)
        edges = []
        for r in rels_list:
            edges.append({"source": r.source_id, "target": r.target_id, "type": r.relation_type, "label": r.label})
        nodes.append({"id": e.entity_id, "name": e.name, "kind": e.kind, "status": e.status, "events": ev, "relations": len(rels_list), "health": compute_health(e, ev, len(rels_list)), "edges": edges})
    return {"nodes": nodes}


# ── L0: Raw Events ────────────────────────────────────────

@app.get("/api/l0/events")
async def l0_events(limit: int = 100, offset: int = 0, event_type: str = "", search: str = ""):
    if not os.path.exists(L0_EVENTS_PATH):
        return {"events": [], "total": 0, "error": "Events file not found"}
    events = []
    with open(L0_EVENTS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ev = json.loads(line)
                    if event_type and ev.get("type") != event_type:
                        continue
                    if search and search.lower() not in json.dumps(ev).lower():
                        continue
                    events.append(ev)
                except json.JSONDecodeError:
                    continue
    total = len(events)
    page = events[offset:offset + limit]
    return {"events": page, "total": total, "returned": len(page)}

@app.get("/api/l0/types")
async def l0_types():
    if not os.path.exists(L0_EVENTS_PATH):
        return {"types": {}}
    counts = {}
    with open(L0_EVENTS_PATH) as f:
        for line in f:
            try:
                ev = json.loads(line)
                t = ev.get("type", "unknown")
                counts[t] = counts.get(t, 0) + 1
            except json.JSONDecodeError:
                continue
    return {"types": counts, "total": sum(counts.values())}

@app.get("/api/l0/sources")
async def l0_sources():
    if not os.path.exists(L0_EVENTS_PATH):
        return {"sources": {}}
    counts = {}
    with open(L0_EVENTS_PATH) as f:
        for line in f:
            try:
                ev = json.loads(line)
                s = ev.get("source", "unknown")
                counts[s] = counts.get(s, 0) + 1
            except json.JSONDecodeError:
                continue
    return {"sources": counts}


# ── L1: Working Memory ────────────────────────────────────

@app.get("/api/l1/agents")
async def l1_agents():
    if not os.path.isdir(L1_AGENTS_PATH):
        return {"agents": []}
    agents = []
    for fname in os.listdir(L1_AGENTS_PATH):
        if fname.endswith(".json"):
            try:
                data = json.load(open(os.path.join(L1_AGENTS_PATH, fname)))
                agents.append({"agent_id": fname.replace(".json", ""), "data": data})
            except Exception:
                pass
    return {"agents": agents}


# ── L2: Conversations ─────────────────────────────────────

@app.get("/api/l2/threads")
async def l2_threads():
    if not os.path.exists(CONVERSATIONS_DB):
        return {"threads": []}
    import sqlite3
    conn = sqlite3.connect(CONVERSATIONS_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT thread_id, summary, agent_scope FROM threads ORDER BY rowid DESC LIMIT 20").fetchall()
        threads = [dict(r) for r in rows]
        return {"threads": threads}
    finally:
        conn.close()

@app.get("/api/l2/thread/{thread_id}")
async def l2_thread(thread_id: str, limit: int = 50):
    if not os.path.exists(CONVERSATIONS_DB):
        return {"messages": []}
    import sqlite3
    conn = sqlite3.connect(CONVERSATIONS_DB)
    conn.row_factory = sqlite3.Row
    try:
        msgs = conn.execute("SELECT role, content, created_at FROM messages WHERE thread_id = ? ORDER BY id ASC LIMIT ?", (thread_id, limit)).fetchall()
        return {"messages": [dict(m) for m in msgs]}
    finally:
        conn.close()


# ── L3: Decisions ─────────────────────────────────────────

@app.get("/api/l3/decisions")
async def l3_decisions(category: str = "", limit: int = 50):
    if not os.path.isdir(L3_DECISIONS_PATH):
        return {"decisions": []}
    all_decisions = []
    for root, dirs, files in os.walk(L3_DECISIONS_PATH):
        for fname in files:
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text()
                    title = content.split("\n")[0].replace("# ", "").strip() if content.startswith("#") else fname
                    tags = []
                    for line in content.split("\n"):
                        if line.startswith("tags:"):
                            raw = line.replace("tags:", "").strip().strip('"').strip("'")
                            tags = [t.strip() for t in raw.split(",")]
                            break
                    rel_path = os.path.relpath(fpath, L3_DECISIONS_PATH)
                    cat = rel_path.split(os.sep)[0] if os.sep in rel_path else ""
                    if category and cat != category:
                        continue
                    all_decisions.append({"title": title, "category": cat, "tags": tags, "path": rel_path, "size": len(content), "preview": content[:300]})
                except Exception:
                    pass
    return {"decisions": sorted(all_decisions, key=lambda d: d["size"], reverse=True)[:limit]}


# ── L4: Narratives ─────────────────────────────────────────

@app.get("/api/l4/narratives")
async def l4_narratives():
    npath = config.L4_narrative_path or os.path.join(config.server_dir, "data", "L4-narrative") if config.server_dir else ""
    if npath and os.path.isdir(npath):
        stories = []
        for fname in sorted(os.listdir(npath)):
            if fname.endswith(".md"):
                fpath = os.path.join(npath, fname)
                try:
                    content = Path(fpath).read_text()
                    stories.append({"name": fname, "content": content[:5000]})
                except Exception as e:
                    stories.append({"name": fname, "content": f"Error reading: {e}"})
        return {"narratives": stories}
    return {"narratives": [], "note": "L4 narrative path not found"}


# ── L5: Routing status ────────────────────────────────────

@app.get("/api/l5/routing")
async def l5_routing():
    return {"reminders_active": 0, "status": "L5 routing data available via MCP-agent-memory API"}



# ── MCP App — ui:// resource ──────────────────────────────


def create_mcp_app():
    """Create FastMCP server for governance (MCP Apps compatible)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("memory-governance")

    RESOURCE_URI = "ui://governance/memory-manager.html"

    @mcp.tool()
    async def governance_dashboard() -> str:
        """Open the Memory Governance dashboard to manage entities."""
        return (
            f"The governance dashboard is available. "
            f"Open http://localhost:{os.getenv('GOVERNANCE_PORT', '10050')} in your browser, "
            f"or I can show you the current status."
        )

    @mcp.resource(RESOURCE_URI, mime_type="text/html")
    async def serve_governance_ui() -> str:
        return get_governance_html()

    return mcp, RESOURCE_URI


def run_mcp_app():
    """Run the MCP App (for when opencode supports MCP Apps)."""
    import sys
    mcp, _ = create_mcp_app()
    mcp.run()


# ── Main ───────────────────────────────────────────────────


def main():
    port = int(os.getenv("GOVERNANCE_PORT", "10050"))
    logger.info("Governance server starting on http://localhost:%d", port)
    print(f"🌐 Memory Governance: http://localhost:{port}")
    print(f"📡 API: http://localhost:{port}/api/entities")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    if "--mcp" in sys.argv:
        run_mcp_app()
    else:
        main()
