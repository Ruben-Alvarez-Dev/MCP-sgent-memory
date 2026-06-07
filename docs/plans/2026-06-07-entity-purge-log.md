# Entity Purge Log — 2026-06-07 (repair plan Phase 3)

Executed `scripts/purge_entities_20260607.py` against `data/entity_timeline.db`.

- Backup (full rows, JSON): `/Users/ruben/MCP-servers/backups/entity-purge-20260607/entity-purge-export.json` (608 KB)
- Targets: 14 regex-junk names (D4: "https", "A", "---", "engra", paths, OCR misspell variants, "current", "test-user") + 8 seed-data names (D6: nexus-backend, ocr-pipeline, jartos-dashboard, browseros-agent, lead-dev, backend-dev, frontend-dev, devops-sre — both the 2026-04-11 and 2026-05-04 copies). 30 entity rows total.

## Counts before → after

| table             | before | after |
|-------------------|-------:|------:|
| entities          | 55     | 25    |
| entity_events     | 9852   | 8085  |
| relations         | 41     | 5     |
| entity_milestones | 9      | 0     |

- `PRAGMA integrity_check`: ok; FTS indexes cleaned by triggers (0 hits for purged content).
- Protected entities verified present after purge: ruben, system, Ruben-Alvarez-Dev, MCP-agent-memory, BrowserOS-OPENCODE, pi-coding-agent.
