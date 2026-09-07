# Tasks — E2E-audit-remediation

- [x] 1.1 Eliminar `await None` de `L3_facts_add_memory` y `L2_search_conversations` (P0-1, P0-3) — criterio: roundtrip add→search OK en protocolo real (`test_protocol_smoke`).
- [x] 1.2 `_ensure_db` idempotente siempre-init (P0-2) — criterio: L2 operativa sobre DB points-first (sandbox + deployment real).
- [x] 1.3 `_delete_one` purga `points_fts` (P0-4) — criterio: `points_fts MATCH` = 0 tras delete en test de protocolo.
- [x] 1.4 `_build_fts5_query` unicode61-faithful (P0-5) — criterio: test unitario de roundtrip FTS + eval sin regresión (R@5 0.5388 / MRR 0.4570).
- [x] 1.5 Red de regresión de protocolo: `tests/e2e/test_protocol_smoke.py` (spawn subprocess + JSON-RPC + sandbox points-first) — criterio: 3/3 en suite por defecto.
- [x] 2.1 Purga de env muertos: generador, `config/.env`, `config/.env.example` (P1-A) — criterio: mcp.json regenerado sin `EMBEDDING_*`/`LLAMA_*`; boot OK.
- [x] 2.2 Instaladores sin stack de embeddings: `bootstrap.sh`, `app-install.sh`, `config.sh`, `verify.sh`, `detect.sh`, `update.sh`, `install.sh`; `services.sh` eliminado — criterio: 0 refs (salvo nota histórica M9), sintaxis OK, config.sh probado en sandbox.
- [x] 2.3 Identidad strict vía Keychain: `scripts/launch-unified.sh`, generador emite launcher, agente `pi-agent` registrado, token SOLO en Keychain (P1-B) — criterio: strict boot + fail-closed verificados en vivo; sha256 registry == Keychain.
- [x] 2.4 Merge a main (`4d5bb88`) + batería completa en main — criterio: 407/0/6 + 151 adversarial.
- [x] 2.5 Certificación de superficie: barrido 54/54 tools en vivo (sandbox) — criterio: 0 crashes; las 3 no-OK son validaciones correctas (whitelists + FS jail).
- [x] 2.6 Scrub de residuos de auditoría en `data/` — criterio: points/threads/fts = 0, grep = 0 tras VACUUM.
