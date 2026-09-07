# GATE — obsidian-kb-pipeline

**Estado:** ⏳ PENDIENTE

## Pre-condiciones de firma

| # | Condición | Evidencia |
|---|-----------|-----------|
| 1 | Grupos A→D completados en orden | tasks.md + commits |
| 2 | KB-01…KB-08 con tests nombrados en verde | pytest -k kb_ |
| 3 | Nota real en `~/.obsidian-vaults/principal/Memory/` visible desde Obsidian | captura E2E |
| 4 | Notas del usuario intactas (hash pre/post) | KB-08 |
| 5 | Cero escrituras a `data/vault`/`data/Lx-persistent` tras el cambio | grep/strace de test E2E |
| 6 | Decisión de migración de huérfanos documentada | tasks E.2 |

## Veredicto

PENDING — el pipeline no se declara vivo hasta que una memoria real del MCP
aparezca en tu Obsidian con formato correcto y sin tocar nada tuyo.
