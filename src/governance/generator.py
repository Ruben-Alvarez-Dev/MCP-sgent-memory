#!/usr/bin/env python3
"""Synthetic Memory Generator — feeds realistic data into Jart-OS memory layers.

Usage:
    python generator.py --days 7 --events 5000 --seed 42

Generates:
  - L0: raw_events.jsonl (bash, agent, system)
  - L0: conversations.db (threads with user/assistant/tool messages)
  - L1: working memory (agent heartbeats)
  - L3: entity_timeline.db (entities, timelines, relations)
  - L3: decision markdown files
  - L2: episodes (episodic memory)
  - L4: narratives
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import random
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger('generator')

# ── Configuration ──────────────────────────────────────────

DEFAULT_SEED = 42
DEFAULT_DAYS = 7
DEFAULT_EVENTS = 5000
BATCH_SIZE = 500

# ── Realistic Templates ────────────────────────────────────

PROJECTS = [
    {"name": "nexus-backend", "kind": "project", "lang": "go", "desc": "API gateway & service mesh"},
    {"name": "ocr-pipeline", "kind": "project", "lang": "python", "desc": "Document OCR extraction pipeline"},
    {"name": "jartos-dashboard", "kind": "project", "lang": "typescript", "desc": "Infrastructure control panel"},
    {"name": "browseros-agent", "kind": "project", "lang": "typescript", "desc": "Browser automation agent"},
]

AGENTS = [
    {"name": "lead-dev", "kind": "agent", "role": "tech lead", "style": "architect"},
    {"name": "backend-dev", "kind": "agent", "role": "backend", "style": "implementer"},
    {"name": "frontend-dev", "kind": "agent", "role": "frontend", "style": "visual"},
    {"name": "devops-sre", "kind": "agent", "role": "devops", "style": "ops"},
]

USERS = ["ruben", "maria", "james", "alex"]

BASH_CMDS = [
    "go build ./cmd/api", "go test ./internal/... -v -count=1",
    "npm run build -- --prod", "npm test -- --coverage",
    "docker compose up -d", "docker compose logs -f api",
    "docker compose restart worker", "docker ps --format 'table {{.Names}}\t{{.Status}}'",
    "kubectl get pods -n production", "kubectl describe pod api-{n}",
    "kubectl logs -f deployment/api -n production",
    "terraform plan -out=plan.tfplan", "terraform apply plan.tfplan",
    "psql -d jartos -c 'SELECT count(*) FROM events'",
    "redis-cli ping", "curl -s http://localhost:8080/health | jq .",
    "curl -X POST http://localhost:10000/api/tiers -H 'Content-Type: application/json' -d '{}'",
    "git status --short", "git log --oneline -10",
    "git diff --stat", "git push origin main",
    "python3 -m pytest tests/ -x -v --timeout=60",
    "python3 -m mypy src/ --strict",
    "python3 -m ruff check src/ --fix",
    "black src/ --line-length=100",
    "pip install -e . -q", "pip freeze | grep fastapi",
    "npx tsc --noEmit --strict",
    "npx prettier --write src/**/*.ts",
    "npx eslint src/ --fix",
    "cargo build --release", "cargo test -- --nocapture",
    "systemctl status jart-os-dashboard",
    "journalctl -u jart-os-vllm --since '1 hour ago'",
    "tail -100 /var/log/jart-os/api.log",
    "df -h /data", "free -h", "htop",
    "ls -la config/", "cat docker-compose.yml | head -40",
    "vim src/main.py", "code src/services/api.py",
    "scp -r build/ user@server:/opt/jart-os/",
    "rsync -avz --progress dist/ deploy@server:/var/www/",
    "make build", "make test", "make deploy-staging",
    "./scripts/migrate-db.sh up", "./scripts/backup.sh",
    "source .venv/bin/activate && uvicorn app.main:app --reload --port 10000",
    "npx ts-node scripts/seed.ts --env=development",
    "gh pr create --title 'feat: add metrics endpoint' --body 'Closes #142'",
    "gh pr review 142 --approve",
    "gh issue list --label bug --limit 5",
    "sleep 2 && echo 'done'",
]

FILE_OPS = [
    "Edit src/api/handlers/users.py — added list_users endpoint",
    "Edit src/services/database.py — optimized connection pooling",
    "Edit src/models/event.py — added timestamp index",
    "Edit src/middleware/auth.py — fixed JWT expiration check",
    "Edit src/utils/config.py — added env override support",
    "Edit src/components/Dashboard.tsx — refactored metrics panel",
    "Edit src/components/Sidebar.tsx — added collapsible sections",
    "Edit src/pages/Settings.tsx — added theme toggle",
    "Edit src/styles/global.css — updated color variables",
    "Edit src/worker/ocr.py — improved image preprocessing",
    "Edit src/worker/extract.py — added table extraction",
    "Edit src/worker/classify.py — updated model weights",
    "Edit docker-compose.yml — added redis service",
    "Edit Dockerfile — optimized layer caching",
    "Edit nginx.conf — added rate limiting",
    "Edit prometheus.yml — added alert rules",
    "Edit grafana/dashboards/api-performance.json — new dashboard",
    "Edit tests/test_api.py — added integration tests",
    "Create src/api/routes/health.py — health check endpoint",
    "Create src/services/cache.py — redis cache wrapper",
    "Create scripts/migration_v2.py — data migration tool",
    "Create docs/api/events.md — API documentation",
    "Delete src/legacy/client.py — deprecated HTTP client",
    "Rename src/utils/helpers.py → src/utils/formatting.py",
]

GIT_OPS = [
    "commit: feat: add pagination to events endpoint",
    "commit: fix: correct JWT token validation",
    "commit: refactor: extract database service layer",
    "commit: test: add integration tests for API",
    "commit: docs: update README with setup instructions",
    "commit: chore: bump version to 2.1.0",
    "commit: feat: implement OCR image preprocessing",
    "commit: fix: handle empty results in search",
    "commit: style: format code with black",
    "branch: feat/user-preferences",
    "merge: feature/ocr-pipeline into main",
    "rebase: main onto release/2.0",
    "tag: v2.1.0",
]

CHAT_TOPICS = [
    # (user_message, assistant_summary)
    ("how do I deploy the new API version?", "Walked through blue-green deployment with docker compose. Created PR #156."),
    ("the database connection keeps dropping", "Diagnosed connection pool exhaustion. Increased max_connections from 20 to 50. Pushed fix."),
    ("can we add rate limiting to the gateway?", "Added nginx rate limiting config (10 req/s). Tested with wrk benchmark. Deployed to staging."),
    ("the OCR pipeline is failing on PDFs", "Found missing dependency: poppler-utils. Updated Dockerfile and redeployed."),
    ("I need a health check endpoint", "Created GET /api/v1/health with DB + Redis + upstream checks. Returns 200/503. Wrote tests."),
    ("let's review the dashboard PR", "Reviewed 12 files. Found 3 issues: missing error handling, untyped state, missing loading state. Approved after fixes."),
    ("add monitoring to the worker queue", "Added Prometheus metrics for queue depth, processing time, error rate. Grafana dashboard created."),
    ("the build is failing on CI", "Fixed: outdated dependency in requirements.txt. Updated fastapi from 0.100 to 0.110. Build green."),
    ("we need a backup strategy for Redis", "Configured Redis RDB snapshots every 15min + AOF. Backup to S3 via cron job. Tested restore."),
    ("users are reporting 502 errors", "Investigated: upstream timeouts. Increased proxy_read_timeout from 30s to 60s. Added retry logic to client."),
    ("migrate the database schema", "Created migration script v2. Added events table + indexes. Ran on staging first. All tests pass."),
    ("can you optimize the search endpoint?", "Added full-text search index on events.content. Query time dropped from 2.3s to 45ms. Added pagination."),
    ("setup staging environment", "Provisioned docker compose overlay for staging. Configured separate DB, Redis, S3 bucket. Smoke tests passed."),
    ("the frontend is slow to load", "Analyzed bundle: 3.2MB → code-split into 4 chunks (412KB main). Added lazy loading for settings page. Lighthouse 54→92."),
    ("add end-to-end tests", "Set up Playwright with 12 test scenarios: login, dashboard, settings, events list. CI pipeline runs them in parallel."),
    ("deploy to production", "Blue-green deploy v2.1.0: 4 instances, zero-downtime. Traffic shifted gradually. Monitored for 15min. All green."),
    ("update the SSL certificates", "Renewed Let's Encrypt certs via certbot. Auto-renew cron job configured. Verified with openssl s_client."),
    ("we have a memory leak", "Profiled with pympler: found unclosed DB connections in worker pool. Added context manager. Memory stable at 240MB."),
    ("I want a canary deployment process", "Set up canary: 10% traffic to new version for 5min. Auto-rollback on 5xx >1%. Smoke tests run before full rollout."),
    ("the API is returning inconsistent errors", "Standardized error response format. All errors now return {error, code, detail, request_id}. Updated 14 endpoints."),
]

DECISIONS = [
    {"title": "Adopt Go for new API gateway", "cat": "architecture",
     "body": "Decision: Rewrite the API gateway in Go. Node.js prototype reached 60% CPU at 2K req/s. Go version handles 15K req/s with 40% less memory. Migration plan: phase 1 = health endpoints, phase 2 = read endpoints, phase 3 = write endpoints. Each phase has a 24h cooldown for monitoring."},
    {"title": "PostgreSQL over MongoDB for event store", "cat": "architecture",
     "body": "Decision: PostgreSQL with partitioning by date. MongoDB was considered for flexible schema but operational complexity outweighed benefits. JSONB columns for variable metadata. Partition by month. Retention: 90 days hot, 1 year cold (S3 via pg_archive). Query patterns are well-defined, not ad-hoc."},
    {"title": "Redis streams for worker queue", "cat": "architecture",
     "body": "Decision: Redis streams over RabbitMQ. Simpler operational footprint (already have Redis), consumer groups handle fan-out well, and the dead-letter mechanism with XACK/XCLAIM is sufficient. Max queue depth: 100K. Processing time SLA: 5s. Alert at 50K depth."},
    {"title": "TypeScript for frontend with strict mode", "cat": "architecture",
     "body": "Decision: TypeScript strict mode enabled. noImplicitAny, strictNullChecks, noUnusedLocals. This caught 47 bugs during migration from JS. Build time increased 15% but production incidents dropped 60%."},
    {"title": "Blue-green deployment strategy", "cat": "architecture",
     "body": "Decision: Blue-green with docker compose. Two full stacks (blue, green). LB switches traffic. Rollback is re-enabling the previous stack. Deploy time: 90s. No downtime. Used for all production services."},
    {"title": "Prometheus + Grafana over Datadog", "cat": "architecture",
     "body": "Decision: Self-hosted Prometheus + Grafana. Datadog was $2.4K/mo for our volume. Prometheus handles 300K series/min. Retention: 15d local, 1y in Thanos (S3). Alertmanager routes to Slack + PagerDuty. Saved $28K/yr."},
    {"title": "Vault for secrets management", "cat": "architecture",
     "body": "Decision: HashiCorp Vault over .env files. Dynamic DB credentials (24h TTL), PKI for mTLS between services, audit log for all secret access. Migration: 2 weeks. All 14 services updated. Zero secrets in git anymore."},
    {"title": "Event sourcing for audit trail", "cat": "architecture",
     "body": "Decision: Event sourcing with append-only log. Every state change is an immutable event. Current table: 8M events, 85GB. Query via materialized views rebuilt every 5min. Enables full audit, point-in-time recovery, and replay for testing."},
]


def write_jsonl(path: str, events: list[dict]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def upsert_sqlite(db_path: str, table: str, data: list[dict], schema: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    for row in data:
        cols = ", ".join(row.keys())
        vals = ", ".join("?" for _ in row)
        conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({vals})", list(row.values()))
    conn.commit()
    conn.close()


def generate(config: argparse.Namespace):
    seed = config.seed or DEFAULT_SEED
    days = config.days or DEFAULT_DAYS
    target_events = config.events or DEFAULT_EVENTS
    rng = random.Random(seed)
    log.info(f"Generator seed={seed} days={days} target_events={target_events}")

    base_time = datetime.now(timezone.utc) - timedelta(days=days)
    server_dir = config.server_dir or os.environ.get("MEMORY_SERVER_DIR", str(Path.home() / "MCP-servers" / "MCP-agent-memory"))

    data_dir = Path(server_dir) / "data"
    l0_path = data_dir / "L0-sensory" / "events.jsonl"
    conv_db = data_dir / "conversations.db"
    timeline_db = data_dir / "entity_timeline.db"
    decisions_dir = data_dir / "L3-semantic" / "decisions"
    episodes_dir = data_dir / "L2-episodic"
    narratives_dir = data_dir / "L4-narrative"

    total_events = 0
    events_buf = []
    conv_schema = """
        CREATE TABLE IF NOT EXISTS threads (thread_id TEXT PRIMARY KEY, summary TEXT DEFAULT '', agent_scope TEXT DEFAULT 'shared', created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, role TEXT, content TEXT, created_at TEXT, tool_calls TEXT);
    """
    timeline_schema = """
        CREATE TABLE IF NOT EXISTS entity_events (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT NOT NULL, timestamp TEXT NOT NULL, event_type TEXT NOT NULL, content TEXT DEFAULT '', metadata TEXT DEFAULT '{}', source_event_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS entity_milestones (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT NOT NULL, milestone TEXT NOT NULL, event_id INTEGER NOT NULL, timestamp TEXT NOT NULL, description TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS entities (entity_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, status TEXT DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT DEFAULT '{}', summary TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS relations (relation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL, relation_type TEXT NOT NULL, source_event_id INTEGER NOT NULL, target_event_id INTEGER NOT NULL, metadata TEXT DEFAULT '{}', created_at TEXT NOT NULL, label TEXT DEFAULT '');
    """

    # Pre-create all directories
    for d in [data_dir / "L0-sensory", decisions_dir / "architecture", episodes_dir, narratives_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Register entities ──────────────────────────
    conn = sqlite3.connect(str(timeline_db))
    conn.executescript(timeline_schema)
    for proj in PROJECTS + AGENTS:
        eid = str(uuid.uuid4())
        now = base_time.isoformat()
        conn.execute("INSERT OR IGNORE INTO entities (entity_id, name, kind, status, created_at, updated_at, metadata, summary) VALUES (?, ?, ?, 'active', ?, ?, '{}', ?)",
                     (eid, proj["name"], proj["kind"], now, now, proj.get("desc", "")))
    conn.commit()
    conn.close()

    def get_eid(name):
        conn2 = sqlite3.connect(str(timeline_db))
        row = conn2.execute("SELECT entity_id FROM entities WHERE name = ?", (name,)).fetchone()
        conn2.close()
        return row[0] if row else None

    # ── Phase 2: Generate events ────────────────────────────
    log.info(f"Generating {target_events} events over {days} days...")
    current_time = base_time
    events_per_day = target_events // days
    day_idx = 0

    while total_events < target_events:
        remaining = target_events - total_events
        batch_size = min(BATCH_SIZE, remaining)
        day_num = day_idx % days
        day_start = base_time + timedelta(days=day_num, hours=rng.randint(8, 18))

        for _ in range(batch_size):
            current_time = day_start + timedelta(
                seconds=rng.randint(0, 28800),
                microseconds=rng.randint(0, 999999)
            )
            ts = current_time.isoformat()
            event_type = rng.choices(
                ["agent_action", "system", "terminal", "file_access", "git_event"],
                weights=[35, 25, 20, 15, 5], k=1
            )[0]

            project = rng.choice(PROJECTS)
            agent = rng.choice(AGENTS)
            content = ""

            if event_type == "terminal":
                content = rng.choice(BASH_CMDS)
                if "{n}" in content:
                    content = content.replace("{n}", str(rng.randint(1, 99)))
            elif event_type == "file_access":
                content = rng.choice(FILE_OPS)
            elif event_type == "git_event":
                content = rng.choice(GIT_OPS)
            elif event_type == "agent_action":
                if rng.random() < 0.3:
                    content = f"call_tool({rng.choice(['read','write','edit','bash','grep','glob'])}, {rng.choice(['src/','config/','tests/','docs/'])})"
                else:
                    content = f"analyze({project['name']}): {rng.choice(['reviewing code','checking logs','running tests','building artifacts','deploying service'])}"
            else:
                content = f"system: {rng.choice(['scheduled task','health check','backup complete','cert renewed','log rotated'])}"

            actor_group = rng.choice(['agent', 'user'])
            if actor_group == 'user':
                actor_id = rng.choice(USERS)
            else:
                actor_id = rng.choice(AGENTS)["name"]

            ev = {
                "event_id": str(uuid.uuid4()),
                "timestamp": ts,
                "type": event_type,
                "source": rng.choice(["terminal", "plugin", "system", "agent", "git", "docker"]),
                "actor_id": actor_id,
                "session_id": f"synth-session-{day_num}-{rng.randint(1,10)}",
                "scope": "",
                "attributes": {"content": content, "event_subtype": event_type},
                "context": {},
            }
            events_buf.append(ev)
            total_events += 1

            # Every 20 events, append to entity timeline
            if total_events % 20 < 1:
                conn3 = sqlite3.connect(str(timeline_db))
                try:
                    eid = get_eid(project["name"])
                    actor_eid = get_eid(agent["name"])
                    if eid:
                        conn3.execute("INSERT INTO entity_events (entity_id, timestamp, event_type, content, source_event_id) VALUES (?, ?, ?, ?, ?)",
                                      (eid, ts, event_type, content[:200], ev["event_id"]))
                    if actor_eid and rng.random() < 0.3:
                        conn3.execute("INSERT INTO entity_events (entity_id, timestamp, event_type, content, source_event_id) VALUES (?, ?, ?, ?, ?)",
                                      (actor_eid, ts, "action", content[:200], ev["event_id"]))
                    conn3.commit()
                finally:
                    conn3.close()

            # Every 100 events, create relation between project and agent
            if total_events % 100 < 1:
                conn4 = sqlite3.connect(str(timeline_db))
                try:
                    peid = get_eid(project["name"])
                    aeid = get_eid(agent["name"])
                    if peid and aeid:
                        existing = conn4.execute("SELECT COUNT(*) FROM relations WHERE source_id=? AND target_id=?",
                                                  (peid, aeid)).fetchone()[0]
                        if existing == 0:
                            rid = str(uuid.uuid4())
                            conn4.execute("INSERT INTO relations (relation_id, source_id, target_id, relation_type, source_event_id, target_event_id, created_at, label) VALUES (?, ?, ?, 'assignment', 0, 0, ?, ?)",
                                          (rid, peid, aeid, ts, f"{agent['role']} on {project['name']}"))
                            conn4.commit()
                finally:
                    conn4.close()

        # Write batch to L0 JSONL
        write_jsonl(str(l0_path), events_buf)
        events_buf = []

        # Every simulated day, generate a conversation thread
        if day_num < days:
            topic = rng.choice(CHAT_TOPICS)
            thread_id = f"synth-{day_num}-{project['name']}-{rng.randint(100,999)}"
            thread_ts = day_start.isoformat()

            # Write to conversations.db
            conn5 = sqlite3.connect(str(conv_db))
            conn5.executescript(conv_schema)
            try:
                conn5.execute("INSERT OR IGNORE INTO threads (thread_id, summary, agent_scope, created_at, updated_at) VALUES (?, ?, 'shared', ?, ?)",
                              (thread_id, topic[0][:80], thread_ts, thread_ts))
                user_msg = topic[0]
                asst_msg = topic[1]
                conn5.execute("INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                              (thread_id, user_msg, thread_ts))
                conn5.execute("INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
                              (thread_id, asst_msg, thread_ts))
                # Add some tool calls
                for _ in range(rng.randint(1, 4)):
                    tool_ts = (day_start + timedelta(seconds=rng.randint(10, 300))).isoformat()
                    conn5.execute("INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, 'tool_call', ?, ?)",
                                  (thread_id, rng.choice(BASH_CMDS), tool_ts))
                conn5.commit()
            finally:
                conn5.close()

        # Every simulated day, generate a decision
        if day_num < min(days, len(DECISIONS)):
            dec = DECISIONS[day_num]
            dec_path = decisions_dir / "architecture" / f"synth-{day_num}-{dec['title'][:30].lower().replace(' ','-')}.md"
            timestamp = (base_time + timedelta(days=day_num, hours=rng.randint(14, 17))).isoformat()
            dec_content = f"""# {dec['title']}

**Date:** {timestamp[:19]}
**Category:** {dec['cat']}
**Source:** synthetic generator

{dec['body']}
"""
            dec_path.write_text(dec_content)

        day_idx += 1
        if day_idx % 1 == 0:
            pct = min(100, int(total_events / target_events * 100))
            log.info(f"  Day {day_num+1}/{days} — {total_events} events generated ({pct}%)")

    # ── Phase 3: Create entity milestones ────────────────────
    conn6 = sqlite3.connect(str(timeline_db))
    for proj in PROJECTS:
        eid = get_eid(proj["name"])
        if eid:
            first = conn6.execute("SELECT MIN(id), timestamp FROM entity_events WHERE entity_id=?", (eid,)).fetchone()
            if first and first[0]:
                conn6.execute("INSERT OR IGNORE INTO entity_milestones (entity_id, milestone, event_id, timestamp, description) VALUES (?, 'created', ?, ?, 'Entity created by synthetic generator')",
                              (eid, first[0], first[1]))
    conn6.commit()
    conn6.close()

    # ── Phase 4: Write episodes ──────────────────────────────
    episodes = []
    for d in range(min(days, 10)):
        proj = PROJECTS[d % len(PROJECTS)]
        ts = (base_time + timedelta(days=d)).isoformat()
        episodes.append({
            "episode_id": str(uuid.uuid4()),
            "timestamp": ts,
            "project": proj["name"],
            "summary": f"Sprint session: {proj['name']} — {proj['desc']}",
            "events_count": events_per_day // len(PROJECTS),
            "outcome": rng.choice(["deployed", "tests passing", "code review pending", "merged", "in review"]),
        })
    ep_path = episodes_dir / "episodes.jsonl"
    write_jsonl(str(ep_path), episodes)

    # ── Phase 5: Write narrative ─────────────────────────────
    narratives_dir.mkdir(parents=True, exist_ok=True)
    narr = f"""# Synthetic Agent Narrative — {days}-Day Simulation

**Period:** {base_time.strftime('%Y-%m-%d')} to {(base_time + timedelta(days=days)).strftime('%Y-%m-%d')}
**Events generated:** {total_events}
**Projects:** {', '.join(p['name'] for p in PROJECTS)}

## Summary

Over the {days}-day simulation period, the system processed development activity across {len(PROJECTS)} projects.
A total of {total_events} events were generated, covering terminal commands, file operations, git actions,
and agent-assisted workflows. The system produced {len(AGENTS)} distinct agent personas working across
teams, with {len(USERS)} human users providing requirements and feedback.

## Key Events

### Day 1 — Foundation
{PROJECTS[0]['name']} bootstrap: repository initialized, CI pipeline configured, basic API scaffold created.
Architecture decision: {DECISIONS[0]['title']}.

### Day 2 — Core Features  
{PROJECTS[1]['name']} development began. Worker service implemented with Redis stream integration.
Database schema migrated. Test coverage reached 72%.

### Day 3 — Integration
{PROJECTS[2]['name']} frontend connected to backend APIs. Real-time dashboard operational.
Integration tests passing. Performance baseline established: 2.3s p95.

### Day 4 — Optimization
Performance improvements across all services. Database query optimization reduced p95 from 2.3s to 45ms.
Frontend bundle reduced from 3.2MB to 412KB. Lighthouse score: 92.

### Day 5 — Deployment
Blue-green deployment pipeline operational. Staging environment provisioned.
Canary deployment process documented. SSL certificates renewed.

### Day 6 — Monitoring
Prometheus + Grafana dashboards created. Alert rules configured for p99 latency, error rate, queue depth.
Vault integration completed. Dynamic database credentials enabled.

### Day 7 — Production
Full production deployment completed. Zero-downtime migration. All services healthy.
Post-mortem: 2 minor incidents, both resolved within 5 minutes.
"""
    (narratives_dir / "synthetic-narrative.md").write_text(narr)

    # ── Count results ────────────────────────────────────────
    total_conv = 0
    conn7 = sqlite3.connect(str(conv_db))
    try:
        total_conv = conn7.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        conn7.close()

    total_ents = 0
    conn8 = sqlite3.connect(str(timeline_db))
    try:
        total_ents = conn8.execute("SELECT COUNT(*) FROM entity_events").fetchone()[0]
        total_rels = conn8.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        total_milestones = conn8.execute("SELECT COUNT(*) FROM entity_milestones").fetchone()[0]
    finally:
        conn8.close()

    log.info(f"\n✅ Generation complete!")
    log.info(f"   L0 events:      {total_events}")
    log.info(f"   L0 messages:    {total_conv}")
    log.info(f"   L3 events:      {total_ents}")
    log.info(f"   L3 relations:   {total_rels}")
    log.info(f"   L3 milestones:  {total_milestones}")
    log.info(f"   L2 episodes:    {len(episodes)}")
    log.info(f"   L3 decisions:   {min(days, len(DECISIONS))}")
    log.info(f"   L4 narratives:  1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jart-OS Synthetic Memory Generator")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Days of history to simulate")
    parser.add_argument("--events", type=int, default=DEFAULT_EVENTS, help="Target L0 event count")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for reproducibility")
    parser.add_argument("--server-dir", type=str, default="", help="MCP-agent-memory server directory")
    args = parser.parse_args()
    generate(args)
