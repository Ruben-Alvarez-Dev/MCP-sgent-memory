# GATE — surgical-memory-ops

**Estado:** ⏳ PENDIENTE — se firma tras completar los grupos A→E en orden.

## Pre-condiciones de firma

| # | Condición | Evidencia requerida |
|---|-----------|---------------------|
| 1 | Grupos A→E completados en orden, sin saltos | tasks.md con checkboxes y commits por grupo |
| 2 | 14 requisitos SURG con test nombrado en verde | pytest -k surgical |
| 3 | Deltas STO-09/10/11 implementados | tests nombrados en spec |
| 4 | G-ISOLATION re-firmada | batería adversarial ampliada ≥161 en verde |
| 5 | Cero regresión | suite completa + protocol smoke |
| 6 | Undo verificado en frío | ejercicio manual documentado: delete masivo → undo → verify() ✅ |
| 7 | UI quirúrgica: dry-run visual imposible de saltar | captura + contract test |

## Veredicto

PENDING — nada de este change llega a main sin GO firmado aquí.
