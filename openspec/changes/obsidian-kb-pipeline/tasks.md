# Tasks — obsidian-kb-pipeline

## Grupo A — Cableado (el triángulo)
- [ ] A.1 Env `MEMORY_OBSIDIAN_VAULT` + `MEMORY_KB_NAMESPACE` en config.py y .env.example — criterio: fallback legacy si vacío
- [ ] A.2 Tools `vault_*` de L3_decisions delegan en VaultManager — criterio: KB-02 verde; cero escrituras directas fuera del manager
- [ ] A.3 Jail de ruta: resolve()+startswith bajo `<vault>/Memory/` — criterio: traversal → 400, test adversarial
- [ ] A.4 Warn al arrancar si el vault no existe o no tiene `.obsidian` — criterio: mensaje accionable, no crash

## Grupo B — Inbox bilingüe
- [ ] B.1 `process_inbox` real: clasificación por tags según README del KB — criterio: KB-03 verde
- [ ] B.2 Espejo EN con marcador `translation: pending` (anti-alucinación: sin LLM no se inventa traducción) — criterio: par ES/EN presente
- [ ] B.3 Test con nota real ES → clasificada + renombrada + espejada — criterio: KB-03 E2E

## Grupo C — Promoción L3→wiki
- [ ] C.1 Hook en consolidación: importance ≥ 0.8 → nota en `Memory/Wiki/` — criterio: KB-04 verde
- [ ] C.2 Índice idempotente `.index.json` (memory_id→path+hash) — criterio: re-consolidar no duplica
- [ ] C.3 Trazabilidad bidireccional frontmatter `source:` ↔ búsqueda — criterio: KB-06 verde

## Grupo D — Integridad con alcance + no-invasión
- [ ] D.1 `integrity_check` limitado al namespace Memory — criterio: KB-05 verde
- [ ] D.2 Adversarial no-invasión: hash pre/post de notas del usuario — criterio: KB-08 verde
- [ ] D.3 Escritura atómica (tmp+rename) en el vault — criterio: sin ficheros parciales bajo kill

## Grupo E — E2E + GATE
- [ ] E.1 E2E completo contra `~/.obsidian-vaults/principal`: captura MCP → L3 → promoción → nota en vault real con espejo — criterio: KB-07 verde
- [ ] E.2 Decisión documentada y aplicada sobre `data/vault` y `data/Lx-persistent` (deprecación/migración) — criterio: cero escrituras futuras a huérfanos
- [ ] E.3 GATE firmado con evidencia + actualización README (sección KB/Obsidian)
