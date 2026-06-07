# Operations Runbook — MCP-agent-memory

Last verified: 2026-06-07 (every procedure below was executed live during the remediation).

## Service map

| Service (launchd) | Port | Role |
|---|---|---|
| com.agent-memory.backpack-api | 8890 | HTTP API daemon (starts via `scripts/run-backpack.sh` → smoke gate) |
| com.agent-memory.qdrant | 6333 | Vector store |
| com.agent-memory.llama-embedding | 8081 | bge-m3 embeddings |
| com.agent-memory.llama-llm | 9000 | qwen2.5-7b summaries |
| com.agent-memory.watchdog | — | Health check + restart, every 5 min |
| com.agent-memory.backup | — | Daily 04:00 verified data snapshot (retention 7) |
| com.agent-memory.lifecycle | — | Weekly Sun 03:00 rotation/purge/Qdrant snapshot |

Monitoring panel: `python3 ~/Code/MCP-agent-memory/audit/monitor/collector.py` → http://127.0.0.1:8895

## Restart a service

```bash
launchctl kickstart -k gui/$(id -u)/com.agent-memory.backpack-api
curl -m 5 http://localhost:8890/api/health   # expect 200 within ~10 s
```

If the daemon refuses to start, check the smoke gate first:
`scripts/smoke.sh` — exit ≠ 0 means the source tree is broken; fix before restarting.

## Hung daemon (port refuses, process alive)

Seen 2026-06-07 during a synchronous heavy consolidation. KeepAlive does NOT
cover hangs; the watchdog's direct :8890 probe does (max 5 min). Manual:
`launchctl kickstart -k ...` as above. Never fire `consolidate {force:true}`
through the HTTP API against a large backlog — run it out-of-band:

```bash
cd ~/MCP-servers/MCP-agent-memory && PYTHONPATH=src .venv/bin/python3 -c "
import asyncio, importlib.util
spec=importlib.util.spec_from_file_location('c','src/L0_to_L4_consolidation/server/main.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(asyncio.run(m.consolidate(force=True)))"
```

## Restore from backup (drilled 2026-06-07: PASS)

```bash
# 1. Stop writers
launchctl bootout gui/$(id -u)/com.agent-memory.backpack-api
# 2. Pick a backup (auto = daily; manual snapshots also in ../backups/)
ls -t ~/MCP-servers/backups/auto/data-*.tar.gz | head -3
# 3. Verify BEFORE replacing
T=$(mktemp -d) && tar -xzf <backup> -C $T && \
  sqlite3 $T/data/conversations.db "PRAGMA integrity_check;" && \
  sqlite3 $T/data/entity_timeline.db "PRAGMA integrity_check;"
# 4. Swap (keep the broken dir until verified)
mv ~/MCP-servers/MCP-agent-memory/data ~/MCP-servers/MCP-agent-memory/data.broken-$(date +%s)
mv $T/data ~/MCP-servers/MCP-agent-memory/data
# 5. Restart + verify
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.agent-memory.backpack-api.plist
curl -m 5 http://localhost:8890/api/health
```

Note: Qdrant vectors are NOT in the data tarball — Qdrant has its own snapshot
rotation (lifecycle, keeps 3). To restore vectors: Qdrant snapshot restore API,
or re-embed from `events.jsonl` (see `audit/` re-embed scripts).

## Known failure signatures

| Symptom | Cause | Action |
|---|---|---|
| `state.json` mtime > 48 h old | Consolidation stalled (F-01 class) | watchdog alerts; run smoke.sh; check backpack.stderr.log |
| Plugin events typed `system` | type_map regression (F-02) | check WARN lines in log: "unmapped event_type" |
| Retrieval returns junk/empty | zero-vector contamination (F-11) | panel sensor S9; run re-embed script |
| L2/L3/L4 counts dropping | lifecycle purge regression (F-12) | restore from snapshot; check lifecycle.log |
| Embedding 500s on batches | batch token overflow | embed ≤10 items per request |
