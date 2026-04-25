# BENCHMARKS — Mediciones Reales del Sistema

> Fecha: 16/04/2026
> Entorno: macOS Apple Silicon, Node v20.20.2, Python 3.10, Qdrant 1.13+

## 1. Embedding Backends

### Latencia por llamada (5 rondas)

| Backend | Promedio | Mín | Máx | Dims | Calidad* |
|---------|----------|-----|-----|------|----------|
| llama.cpp subprocess (bge-m3) | 1,087ms | 1,071ms | 1,095ms | 1024 | Excelente |
| llama.cpp server mode (bge-m3) | **15ms** | 11ms | 27ms | 1024 | Excelente |
| llama.cpp nomic-embed-text (warm) | 27ms | — | — | 768 | Pobre |
| llama.cpp nomic-embed-text (cold) | 1,459ms | — | — | 768 | Pobre |

**Speedup subprocess → server: 72.5x**

### Calidad de discriminación semántica (cosine similarity)

| Par de textos | bge-m3 | nomic | Ideal |
|---------------|--------|-------|-------|
| Relevante vs Relevante ("prefiere español" vs "preferencia idioma español") | **0.7213** | 0.5585 | >0.7 |
| Relevante vs Irrelevante ("prefiere español" vs "npm install error") | **0.3145** | 0.6497 | <0.4 |
| Separación (relevante - irrelevante) | **0.4068** ✅ | -0.0912 ❌ | >0.3 |

**Conclusión:** bge-m3 tiene 4.5x mejor separación que nomic. **Mantener bge-m3.**

## 2. Operaciones MCP via Gateway

### Rendimiento por operación (3 rondas)

| Operación | Server MCP | Promedio | Mín | Máx |
|-----------|-----------|----------|-----|-----|
| heartbeat | automem | 171ms | 151ms | 193ms |
| store (memorize) | automem | 1,459ms | 1,380ms | 1,509ms |
| ingest_event | automem | 1,449ms | 1,400ms | 1,513ms |
| recall (request_context) | vk-cache | 1,594ms | 1,507ms | 1,646ms |
| search | mem0-bridge | 1,480ms | 1,357ms | 1,544ms |
| save_decision | engram-bridge | 158ms | 148ms | 176ms |
| save_conversation | conv-store | 210ms | — | — |
| vault_write | engram-bridge | 173ms | — | — |
| think | seq-thinking | 159ms | 147ms | 170ms |
| consolidate (force) | autodream | 287ms | — | — |
| check_reminders | vk-cache | 155ms | — | — |
| push_reminder | vk-cache | 1,599ms | — | — |
| dismiss_reminder | vk-cache | 146ms | — | — |

### Desglose de latencia store (1,459ms)

```
Subtotal subprocess embedding: ~1,087ms (74.5%)
Subtotal Qdrant write:         ~300ms (20.6%)
Subtotal JSONL append:         ~50ms  (3.4%)
Subtotal overhead MCP:         ~22ms  (1.5%)
```

**Cuello de botella = subprocess embedding (74.5% del tiempo total)**

## 3. Búsqueda Directa en Qdrant (sin MCP)

| Query | Score mejor | Resultados | Nota |
|-------|------------|------------|------|
| "idioma preferencia español" | 0.697 | 3/8 | ✅ Correcto |
| "error permisos npm" | — | — | No medido |
| "gestor paquetes decisión" | 0.359 | 3/8 | ✅ Correcto |

## 4. Estado de Datos

| Colección | Puntos | Raw events | Consolidaciones |
|-----------|--------|------------|-----------------|
| automem | 11 | 44 JSONL | 0 |
| mem0_memories | 0 | — | — |
| conversations | 0 | — | — |
| Engram decisiones | ~2 dirs | — | — |
| Vault notas | 0 | — | — |

## 5. Predicción Post-Optimización

| Operación | Actual | Con server mode | Con cache |
|-----------|--------|----------------|-----------|
| store | 1,459ms | ~50ms (29x) | ~50ms |
| recall | 1,594ms (roto) | ~50ms (funcional) | ~5ms |
| search | 1,480ms | ~40ms (37x) | ~3ms |
| heartbeat | 171ms | 171ms (sin cambio) | 171ms |
| save_decision | 158ms | 158ms (sin cambio) | 158ms |

*Operaciones sin embedding (heartbeat, decision, vault) no se ven afectadas.*

---

*Datos recopilados con 17 tests secuenciales + 3 rondas de benchmark.*
