# Evidence — E2E-audit-remediation (2026-09-07)

## Auditoría (pre-fix)

| Prueba | Resultado |
|--------|-----------|
| Suite completa | 403 passed / 0 failed / 6 skipped |
| Adversarial | 151/151 |
| Barrido 12 tools críticas en vivo | 💥 `add_memory` (await None), 💥 L2 save/get/list (no such table: threads), 💥 `search_conversations` (await None) |
| Causa raíz P0-2 | `_ensure_db`: `if not os.path.exists(path): _init_db()` — DB points-first nunca crea `threads` |
| Retención | `points_fts_content` conservaba contenido de points borrados; 0 triggers en DB |

## Remediación (post-fix)

| Prueba | Resultado |
|--------|-----------|
| Suite completa | **407 passed / 0 failed / 6 skipped** (en feat y en main) |
| Adversarial | **151/151** |
| Eval retrieval | **R@5 = 0.5388 / MRR = 0.4570** (48 queries) — idéntico al pre-fix, cero regresión |
| Protocol smoke (`tests/e2e/test_protocol_smoke.py`) | 3/3 — spawn subprocess real + JSON-RPC + sandbox points-first |
| CRUD en deployment real | **8/8** (antes 5/7) |
| Barrido 54/54 tools (sandbox) | 51 OK + 3 validaciones correctas (whitelists, FS jail) — **0 crashes** |
| Strict en vivo | boot + health + tool call OK; fail-closed para agente sin credencial; sha256 registry == Keychain |
| Scrub `data/` | points/threads/fts = 0; grep marcadores = 0 tras VACUUM |
| Instaladores | 0 refs embedding (salva nota histórica); sintaxis OK; `config.sh` probado en sandbox |

## Commits

- `69196e7` — fix(P0): await-None + schema healing + FTS purge + alnum tokens + protocol smoke
- `4d5bb88` — feat(P1): env purgado + identidad strict vía Keychain
- (este change) — instaladores purgados + README + documentos de cierre
