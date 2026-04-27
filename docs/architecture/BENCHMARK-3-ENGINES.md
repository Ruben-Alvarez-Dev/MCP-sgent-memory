# Benchmark Comparativo: 3 Engines × 20 Pruebas

**Fecha:** 2026-04-27
**Máquina:** MacBook Pro M1, 32 GB RAM, macOS
**Modelos:** qwen2.5-7b-instruct (LLM) + bge-m3 / nomic-embed-text (Embeddings)

---

## 1. Configuración del Test

| Engine | LLM | Embeddings | Puerto LLM | Puerto EMB |
|---|---|---|---|---|
| **llama.cpp** (Metal) | qwen2.5-7b-instruct-Q4_K_M.gguf | bge-m3-q8_0.gguf | 8080 | 8081 |
| **Ollama** | qwen2.5:7b | nomic-embed-text | 11434 | 11434 |
| **LM Studio** | qwen2.5-7b-instruct | text-embedding-nomic-embed-text-v1.5 | 1234 | 1234 |

Todos usan el mismo modelo base (Qwen 2.5 7B instruct) en formato GGUF.
Embeddings: bge-m3 (1024-dim) vs nomic-embed-text (768-dim) — familias diferentes.

---

## 2. Resultados LLM (10 pruebas por engine)

### 2.1 Latencia y Throughput

| Test | Descripción | llama.cpp | Ollama | LM Studio |
|---|---|---|---|---|
| LLM-01 | Respuesta simple ES | **364ms** (19.3 t/s) | 17,458ms (0.4 t/s) | 17,811ms (0.4 t/s) |
| LLM-02 | Resumen | **1,639ms** (42.7 t/s) | 1,738ms (40.9 t/s) | 1,747ms (41.8 t/s) |
| LLM-03 | Código Python | **2,697ms** (49.7 t/s) | 4,193ms (47.7 t/s) | 4,198ms (47.6 t/s) |
| LLM-04 | JSON forzado | **1,609ms** (49.7 t/s) | 1,929ms (42.0 t/s) | 1,788ms (45.3 t/s) |
| LLM-05 | Input largo (737 tok) | **312ms** (48.0 t/s) | 1,832ms (9.3 t/s) | 1,974ms (8.6 t/s) |
| LLM-06 | Generación larga (256 tok) | **5,193ms** (49.3 t/s) | 5,287ms (48.4 t/s) | 5,310ms (48.2 t/s) |
| LLM-07 | Razonamiento lógico | **3,020ms** (49.7 t/s) | 3,214ms (46.7 t/s) | 3,201ms (46.9 t/s) |
| LLM-08 | Consistencia (3×, temp=0) | **231ms** ✅ idénticas | 298ms ✅ idénticas | 242ms ✅ idénticas |
| LLM-09 | Clasificación intent | **71ms** ✅ correcta | 255ms ✅ correcta | 203ms ✅ correcta |
| LLM-10 | Benchmark 10× avg | **31.8 tok/s** (σ=0.3) | 22.1 tok/s (σ=1.6) | 28.5 tok/s (σ=2.4) |

### 2.2 Hallazgos LLM

- **Cold start**: llama.cpp 48× más rápido (364ms vs 17,458ms). Ollama y LM Studio cargan el modelo bajo demanda.
- **Input largo**: llama.cpp 6× más rápido (312ms vs 1,832ms). Los otros engines procesan el input más lentamente.
- **Generación warm**: comparable entre los tres (~48 tok/s para generación larga).
- **Calidad**: idéntica en los tres (mismo modelo base Qwen 2.5 7B).
- **Consistencia**: los tres producen resultados idénticos con temp=0.
- **Clasificación**: los tres clasifican correctamente como `decision_recall`.

---

## 3. Resultados Embeddings (10 pruebas por engine)

### 3.1 Latencia y Calidad

| Test | Descripción | bge-m3 (llama.cpp) | nomic (Ollama) | nomic-v1.5 (LM Studio) |
|---|---|---|---|---|
| EMB-01 | Básico ("Hello world") | **47ms**, dim=1024 | 13,278ms, dim=768 | 11,138ms, dim=768 |
| EMB-02 | Similitud alta (ES) | **cos=0.8043**, 27ms | cos=0.7543, 178ms | cos=0.6554, 106ms |
| EMB-03 | Similitud baja | **cos=0.5314**, 43ms | cos=0.7222, 37ms | cos=0.5796, 22ms |
| EMB-04 | Cross-lingual EN→ES | **cos=0.9186**, 39ms | cos=0.4418, 49ms | cos=0.5838, 18ms |
| EMB-05 | Palabra única | **19ms** | 38ms | 91ms |
| EMB-06 | Texto largo (~300 words) | **58ms** | 99ms | 140ms |
| EMB-07 | Texto vacío | **15ms** ✅ | 34ms ✅ | 8ms ✅ |
| EMB-08 | Batch 5 textos | 90ms (18ms/t) | 83ms (17ms/t) | **34ms** (7ms/t) |
| EMB-09 | Benchmark 20× avg | 33.3/s (30ms) | 51.5/s (19ms) | **96.8/s** (10ms) |
| EMB-10 | Determinismo (3×) | **✅ 1.000000** | **✅ 1.000000** | ❌ NO determinista |

### 3.2 Gap Semántico (métrica clave para calidad de búsqueda)

| Modelo | Similitud alta | Similitud baja | Gap | Cross-lingual |
|---|---|---|---|---|
| **bge-m3** | 0.8043 | 0.5314 | **0.2729** | **0.9186** |
| nomic (Ollama) | 0.7543 | 0.7222 | 0.0321 | 0.4418 |
| nomic (LM Studio) | 0.6554 | 0.5796 | 0.0758 | 0.5838 |

### 3.3 Hallazgos Embeddings

- **bge-m3 tiene 8.5× más separación semántica** que nomic (Ollama). Esto significa búsquedas mucho más precisas.
- **bge-m3 es el ÚNICO truly cross-lingual**: 0.9186 EN↔ES vs 0.44 de nomic. Nomic directamente no entiende español.
- **LM Studio embeddings NO son deterministas**: el mismo texto produce vectores ligeramente diferentes. Inaceptable para memoria.
- **Cold start**: bge-m3 282× más rápido (47ms vs 13,278ms). Los otros cargan el modelo bajo demanda.
- **Warm throughput**: LM Studio gana en velocidad pura (96.8/s) pero pierde en calidad y determinismo.

---

## 4. Uso de Recursos

| Engine | RAM LLM | RAM Embeddings | RAM Total | Notas |
|---|---|---|---|---|
| **llama.cpp** | 4,886 MB | 344 MB | **5,230 MB** | Siempre cargado, Metal GPU |
| Ollama | ~4,700 MB (lazy) | ~274 MB (lazy) | ~5,000 MB | Carga bajo demanda |
| LM Studio | ~4,700 MB (lazy) | ~300 MB (lazy) | ~5,000 MB | Carga bajo demanda |

Nota: Ollama y LM Studio liberan RAM tras keep_alive (5min default). llama.cpp mantiene el modelo siempre cargado.

---

## 5. Conclusión

Para el sistema MCP-agent-memory, **llama.cpp + bge-m3 es la elección correcta**:

1. **48× más rápido en cold start** — crítico para respuestas en tiempo real
2. **8.5× mejor separación semántica** — búsquedas precisas vs basura
3. **Cross-lingual real** (0.92) — nomic no funciona en español (0.44)
4. **Determinismo perfecto** — LM Studio falla aquí
5. **Always-loaded** — sin latencia de carga bajo demanda

Ollama y LM Studio son mejores para uso interactivo humano (carga/descarga modelos, interfaz gráfica) pero inferiores como backend para un sistema de memoria automático que necesita respuestas consistentes y rápidas.
