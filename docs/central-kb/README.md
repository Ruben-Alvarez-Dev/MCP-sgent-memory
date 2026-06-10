# Jart-OS Knowledge Stack (JKS) — Documento de Diseño

Version 0.1 | 2026-05-29

## Vision General

Sistema unificado de gestion del conocimiento personal para el humano y los agents Jart-OS.

Funciones:
- Indexar originales sin moverlos
- Destilar conocimiento en Markdown + YAML
- Publicar en Obsidian navegable
- Indexar en backends vectorial, de grafos y de texto
- Federar para que todos los agents compartan memoria
- Versionar en Git con backup a 3 ubicaciones
- Permitir intervencion humana directa

Principios: los originales no se mueven, el Markdown es fuente de verdad, el humano tiene control, sectorizado por dominio, versionado y trazable.

## Arquitectura

CAPA DE PRESENTACION: humano desde Obsidian, agents desde MCP.
CAPA DE CONOCIMIENTO: repositorio Git con carpetas por dominio, decisiones, reglas, procedimientos, patrones, especificaciones.
CAPA DE INDICES: tres backends complementarios, todos regenerables desde el Markdown.
CAPA DE FEDERACION: misma identidad de usuario en todos los agents.
CAPA DE ORIGINALES: los archivos originales no estan en el repo. Viven donde siempre. Un CSV los referencia con checksum.

## Estructura

~/knowledge/ con README, config, catalog, domains/, decisions/, rules/, procedures/, patterns/, specs/, templates/, vault/, raw/, scripts/, docs/.

## Formato de Entrada

Cada entrada es un .md con frontmatter YAML: id, tipo, dominio, estado, confianza, sensibilidad, fuente original (tipo, URI, checksum), tags, relaciones, fechas, supersesiones, metricas.

Cuerpo en Markdown con wikilinks. La fuente referencia al original sin copiarlo.

## Pipeline

Descubrimiento en catalogo, ingesta y extraccion de texto, destilacion mediante LLM local, indexacion en los tres backends, revision humana en Obsidian, publicacion con Git, mantenimiento periodico (scoring de confianza, olvido programado, supersesion).

## Sectorizacion

Por dominio (carpetas independientes), por usuario/agent (scope en frontmatter), por catalogo (indice de entradas + indice de originales), por estado (agents ven publicado, humano ve todo).

## Control Humano

El humano puede editar cualquier entrada en Obsidian, cambiar su estado, censurar contenido y hacer commit. Los cambios se propagan a los indices.

El agente escribe en borrador. Para publicar necesita validacion automatica de formato, sanitizacion de datos, y revision humana.

## Ciclo de Vida

Siete estados: raw, draft, reviewed, published, amended, deprecated, redacted.

Confidence scoring por fuentes, recencia, contradicciones, accesos y decaimiento. Supersesion: nueva invalida vieja. Forgetting: no accesadas pasan a deprecated. No se borran.

## Backups

Markdown es fuente de verdad. Indices regenerables. Tres destinos Git: nube (GitHub), servidor local (Mac Mini), backup frio.

## Integracion Jart-OS

TIER-08 KNOWLEDGE alberga los servicios. Las cinco capas de memoria Jart-OS se integran con los niveles de persistencia del stack.

## Backends

Tres complementarios: vectorial (significado), grafos (relaciones), texto (palabras clave). Consulta paralela con fusion de resultados.

## Fuentes y Referencias

### Verificadas en la sesion del 2026-05-29

- Karpathy, A. (2026). LLM Wiki. gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Chunxiaoxx (2026). Compass v1.0 OSS. dev.to/chunxiaoxx/compass-v10-oss-released-cross-agent-memory-federation
- Mem0 (2026). State of AI Agent Memory 2026. mem0.ai/blog/state-of-ai-agent-memory-2026
- Chen et al. (2026). MemForest. arXiv:2605.23986. arxiv.org/abs/2605.23986
- Ma et al. (2025). Nemori. arXiv:2508.03341. arxiv.org/abs/2508.03341
- Hu et al. (2026). xMemory. arXiv:2602.02007. arxiv.org/abs/2602.02007
- Liu et al. (2026). HMO. arXiv:2604.01670. arxiv.org/abs/2604.01670
- Yang et al. (2026). Graph-based Agent Memory Survey. arXiv:2602.05665. arxiv.org/abs/2602.05665
- Rohit G. (2026). LLM Wiki v2. gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2

### Leidas del proyecto local

- Jart-OS Canonical Spec v3.0.0. Code/Jart-OS/documentation/JART-OS-CANONICAL-SPEC.md
- MCP-agent-memory THE-BACKPACK-EXPLAINED.md. docs/architecture/

### Otras referencias de la sesion

- MCP for RAG and Agent Memory. Knit (abr 2026). getknit.dev
- AI Agent Protocols 2026. RUH. ruh.ai
- Frontiers Research Topic. Memory, Knowledge Updating, Evolution in AI Agents. Jul 2026.
- MCP vs A2A Guide. DEV (mar 2026). dev.to/pockit_tools
- The New Stack. Agentic knowledge base patterns. thenewstack.io

## Anexo: Tipos de Documentos Soportados

Cada formato de original tiene su propia ruta de ingesta, pero todos producen el mismo formato de salida: .md con frontmatter.

### Documentos de texto

| Tipo | Extensiones | Ingesta | Destilación | Particularidades |
|------|-------------|---------|-------------|-----------------|
| PDF | .pdf | LlamaParse / marker / pypdf | LLM extrae resumen, reglas, decisiones, entidades | Preservar jerarquía (TOC, secciones) si es libro técnico. Para papers: extraer abstract, contribuciones, metodología, conclusiones. |
| EPUB/MOBI | .epub .mobi | calibre (ebook-convert) a markdown | Misma que PDF | Conversión previa a .md, después se procesa como markdown directamente |
| DOCX/ODT | .docx .odt | pandoc a markdown | Misma que PDF | Útil para apuntes y documentos ofimáticos |
| Markdown | .md .markdown | Directo | Validar frontmatter, extraer entidades y relaciones | Si ya tiene frontmatter, preservarlo y complementarlo. Si no, generarlo. |

### Web y URLs

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Artículo web | trafilatura / Jina Reader | LLM extrae contenido principal | Ignorar menús, ads, footers. Conservar fecha de publicación. |
| Foro / Thread | trafilatura + extracción de hilo | Resumen de hilo + respuestas clave | Preservar estructura de replies. Identificar la respuesta aceptada o más votada. |
| Documentación técnica | trafilatura + preservar jerarquía de headers | Misma que PDF | Importante preservar la navegación por secciones. |
| Bookmark (Chrome/Firefox) | Exportar HTML de bookmarks → trafilatura cada URL | Por lote o individual | El catalog.csv los agrupa por carpeta de origen. Se pueden procesar en batch. |
| Página con código (GitHub, docs) | trafilatura + extraer bloques de código | Resumen técnico + fragmentos de código | Preservar lenguaje y contexto del código. No truncar ejemplos. |

### Audio

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Podcast / Charla | Whisper (whisper.cpp) → transcripción | LLM sobre la transcripción | Whisper produce timestamps. Para podcasts largos (>1h), chunkear por temas. |
| Reunión / Clase | Whisper → transcripción + diarización (quién habla) | Resumen + decisiones + acción | Diarización opcional (necesita modelo separado). Si no, resumen plano. |
| Nota de voz | Whisper | Misma que podcast | Fragmentos cortos (<5 min), destilación directa. |

### Video

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Charla técnica | ffmpeg frames (1/30s) + Whisper | Modelo multimodal ve frames + oye audio → resumen visual+textual | Diagramas, código en pantalla, slides. Los frames relevantes se guardan como assets. |
| Tutorial | ffmpeg frames (1/15s, más densidad) + Whisper | Pasos, comandos, resultados visuales | Mayor densidad de frames para capturar acciones rápidas. |
| Música / Concierto | Whisper + análisis de metadatos (si aplica) | Notas sobre la pieza, género, estructura | No necesita modelo multimodal, solo metadata + resumen textual. |
| Video sin diálogo (demostración visual) | ffmpeg frames (1/10s) | Modelo multimodal describe lo visual | Sin Whisper. Solo frames. |

### Imágenes

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Diagrama técnico | Modelo multimodal (Gemini/local) describe el diagrama | Nota técnica sobre el contenido del diagrama | Ideal para arquitecturas, flujos, mapas conceptuales. |
| Captura de pantalla | OCR (si tiene texto) + descripción visual | Nota sobre lo que muestra la captura | OCR con marker o tesseract para texto. |
| Foto de documento | OCR + modelo multimodal | Texto extraído + descripción | Para pizarras, notas manuscritas, fotos de libros. |
| Infografía | Modelo multimodal describe estructura y datos | Resumen de la infografía | Preservar datos numéricos y relaciones visuales. |

### Código y proyectos

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Repositorio Git | Leer README + estructura + archivos clave | Resumen técnico: propósito, stack, arquitectura, setup | No indexar todo el código. Solo la documentación y la estructura. |
| Script / Fragmento | Directo como .md con bloque de código | Nota técnica: qué hace, cómo usarlo, dependencias | Preservar el código literal. Añadir frontmatter con lenguaje y propósito. |
| Documentación de API | Leer endpoints, schemas, ejemplos | Referencia rápida de la API | Para APIs que usás seguido. No duplicar la doc oficial, solo lo que necesitás. |

### Conversaciones con agents

| Tipo | Ingesta | Destilación | Particularidades |
|------|---------|-------------|-----------------|
| Sesión de trabajo con pi/Claude/Cursor | Exportar conversación como JSONL o markdown | Extraer: decisiones, reglas, descubrimientos, patrones | El agente ya debería haber guardado L3_decisions automáticamente. Si no, extraer manual. |
| Prompt + respuesta valiosa | Copiar como .md | Preservar el prompt y la respuesta como referencia | Marcar como tipo "conversation". Linkear a la decisión o descubrimiento que generó. |

### Combinaciones y formatos híbridos

| Tipo real | Cómo se procesa |
|-----------|----------------|
| PDF con capturas de pantalla | LlamaParse extrae el texto. Las imágenes incrustadas se envían a modelo multimodal para describirlas. Todo se fusiona en un solo .md. |
| Video de tutorial con código | Whisper transcribe. Frames capturan el código en pantalla. OCR extrae el código de los frames. Todo se fusiona: "en el minuto 10:23 escribe X comando que hace Y". |
| Webinar con slides (PDF + video) | Se procesan por separado. La entrada final en domains/ linkea ambas fuentes: "Este resumen combina el video del webinar (kb-ia-0050) y las slides (kb-ia-0051)". |
| Bookmark a un thread de Twitter/X | trafilatura extrae el hilo completo. El LLM lo resume identificando: idea principal, ejemplos, reacciones relevantes. |
| Nota manuscrita escaneada | OCR (marker/tesseract) + modelo multimodal describe diagramas/dibujos. |

### Lo que produce cada entrada

Sin importar el tipo de original, la salida es siempre:

```
.md con frontmatter → Qdrant + SurrealDB + Engram + Obsidian
```

Los únicos campos que cambian según el tipo son:

```yaml
source:
  type: pdf | url | audio | video | image | code | conversation | bookmark | note
  # El resto del frontmatter es idéntico para todos los tipos
```

El pipeline es el mismo. Cambia solo el paso de ingesta (cómo se extrae el texto/frames/estructura del original).

### Ejemplo para cada tipo

```yaml
# PDF
source: { type: pdf, uri: "/Drive/libros/attention.pdf", checksum: sha256:a3f8c... }

# URL
source: { type: url, uri: "https://arxiv.org/abs/2605.23986", checksum: null }

# Video
source: { type: video, uri: "/Drive/videos/talk.mp4", checksum: sha256:b2d1a...,
          duration: "45:22", frames_extracted: 90 }

# Audio
source: { type: audio, uri: "/Drive/podcast/episodio.mp3", checksum: sha256:c3e2b...,
          duration: "1:23:15", transcript_model: "whisper" }

# Imagen
source: { type: image, uri: "/Drive/diagramas/arquitectura.png", checksum: sha256:d4f3c...,
          visual_model: "qwen3-vl" }

# Bookmark
source: { type: bookmark, uri: "https://herramienta-x.com", checksum: null,
          bookmark_folder: "IA/Herramientas" }

# Conversación con agente
source: { type: conversation, uri: "pi-session-2026-05-29", checksum: null,
          agent: "pi/el-gentleman", session_id: "ses_abc123" }

# Código
source: { type: code, uri: "/Code/MCP-agent-memory/src/shared/hybrid_qdrant.py",
          checksum: sha256:e5g4d..., language: "python", lines: 168 }
```

### Rendimiento estimado por tipo

| Tipo | Tiempo ingesta (1 unidad) | LLM llama-level | Ocupa en repo |
|------|:------------------------:|:---------------:|:-------------:|
| PDF (50 págs) | ~3-8 min | Sí (destilación) | ~10 KB |
| EPUB (libro 300 págs) | ~5-10 min | Sí | ~30 KB |
| URL artículo | ~1-2 min | Sí | ~5 KB |
| Audio (1h) | ~5 min Whisper + ~3 min LLM | Sí (Whisper GPU + LLM) | ~8 KB |
| Video (30min) | ~5 min Whisper + ~2 min frames + ~5 min multimodal | Sí (modelo vision) | ~10 KB + frames (opcional) |
| Imagen (1) | ~30 seg (modelo vision) | Sí | ~3 KB |
| Bookmark (1) | ~30 seg | Sí (chunk de URLs) | ~2 KB |
| Conversación (1 sesión) | Inmediato (ya es texto) | Sí (extraer decisiones) | ~5 KB |
| Código (archivo) | ~30 seg | Sí (resumir) | ~3 KB |
| Markdown/Nota | Inmediato | No (solo validar + indexar) | la que ya tenga |

### Lo que NO se indexa

Por política de diseño, estos contenidos no pasan por el pipeline:

- Archivos binarios sin contenido semántico (.dmg, .app, .zip comprimido)
- Librerías, dependencias, node_modules
- Archivos temporales o de caché
- Música sin valor documental (discos completos, mixes sin notas)
- Lo que el humano decida explícitamente no indexar

Si algún día cambia la necesidad, se añade el tipo al pipeline.

## Apps y Servicios

### Las que YA EXISTEN y se usan

| App/Servicio | Ubicación | Puerto | Para qué |
|-------------|-----------|:------:|----------|
| Qdrant | Mac Mini | 6333 | Vector DB (búsqueda semántica) |
| Engram | Mac Mini | 7437 | SQLite+FTS5 (búsqueda rápida) |
| MCP-agent-memory | Workstation + Mac Mini | stdio MCP | 53 tools, L0-L5, backpack |
| MCP-agent-research | Workstation (construido) | stdio MCP | Búsqueda unificada multi-provider (pendiente de configurar en pi) |
| Obsidian | Workstation | — | Vault navegable + edición humana |
| llama-server | Mac Mini | 8081 | BGE-M3 embeddings |
| Git | Ambos | — | Versionado |
| Tailscale | Ambos | — | VPN mesh |

### Las que se INSTALAN nuevas

| App/Servicio | Instalación | Puerto | Máquina | Prioridad |
|-------------|-------------|:------:|---------|:---------:|
| SurrealDB | docker run surrealdb/surrealdb | 10807 | Mac Mini | Fase 1 |
| Compass | pip install nautilus-compass | 10808 | Mac Mini + c/ cliente | Fase 1 |
| git-crypt | brew install git-crypt | — | Ambos | Fase 1 |
| trafilatura | pip install trafilatura | — | Workstation (bajo demanda) | Fase 2 |
| LlamaParse | API key (opcional) | — | Workstation (bajo demanda) | Fase 2 |
| ffmpeg | brew install ffmpeg | — | Workstation | Fase 2 (video) |

### Las que NO se instalan como servicios dedicados (de momento)

RAGFlow, LlamaIndex, R2R, AnythingLLM, Affine no se montan como servicios ahora. Si en el futuro se necesita RAG raw sobre PDFs sin destilar, se evalúa RAGFlow como herramienta de consulta complementaria. El pipeline principal de conocimiento es JKS (destilación → .md → índices). RAG raw y JKS conviven: el primero para consultas exploratorias sobre originales sin procesar, el segundo para conocimiento curado y trazable.

---

## Orden de Montaje (Fase 1)

### Día 1: Repositorio y formato

1. Crear ~/knowledge/ con domains/, decisions/, rules/, procedures/, patterns/, templates/, vault/, raw/
2. git init + git remote add a GitHub y Mac Mini
3. Configurar .gitattributes para git-crypt
4. Abrir vault/ como vault de Obsidian
5. Crear catalog.csv
6. Escribir primera entrada a mano: domains/ia/kb-001.md

### Día 2: Servicios

7. Arrancar SurrealDB en Mac Mini (docker-compose, puerto 10807)
8. pip install nautilus-compass + configurar MCP en pi (puerto 10808)
9. Verificar Qdrant y Engram corriendo
10. Hacer git push a Mac Mini

### Día 3: Pipeline

11. Escribir ingest.sh: toma un archivo, lo procesa según su tipo, escribe .md, indexa
12. Probar con PDF, URL, nota markdown
13. Ajustar prompt de destilación
14. index.sh: toma los .md y los indexa en Qdrant + SurrealDB + Engram

### Día 4: Cierre

15. Escribir sync.sh: git push/pull automático
16. Cron en Mac Mini: git pull + re-indexar cada hora
17. Configurar Compass en Claude Desktop y Cursor
18. Probar censura con redact.sh

### Fase 2 (siguiente semana)

19. Pipeline multimodal: ffmpeg frames + Whisper + modelo vision para video
20. Pipeline batch: procesar montañas de documentos existentes
21. Confidence scoring periódico
22. Benchmarks (LoCoMo, LongMemEval, BEAM)

### Fase 3 (próximo mes)

23. Review gate automatizado
24. Forgetting programado
25. Supersession automática
26. Obsidian Sync para móvil/tablet (o solución alternativa)

---

## Integración Completa con Jart-OS

### Las 5 capas de memoria

| Capa Jart-OS | Backend | Lo que JKS hace |
|-------------|---------|----------------|
| 1. AGENT (contexto inmediato del agente) | LanceDB | MCP-agent-memory L0-L5 (53 tools, backpack) |
| 2. UNIT (sesión tri-unit) | SQLite | conversations_* en Qdrant |
| 3. DOMAIN (conocimiento específico) | Qdrant "opo" | domains/ en Markdown + Qdrant + SurrealDB |
| 4. GLOBAL (ADRs, lecciones) | Qdrant "global" | decisions/ + rules/ |
| 5. RAG (PDFs ingeridos) | Qdrant "study" | Pipeline destilación → Markdown + Qdrant. RAGFlow opcional para raw. |

### Los 10 Tiers de Jart-OS (dónde cae cada cosa)

| Tier | Nombre | Qué va aquí |
|:----:|--------|-------------|
| 00 | METAL | llama-server, engines locales |
| 01 | SECURITY | ya existente |
| 02 | GATEWAY | MCP servers |
| 03 | SERVICES | Redis, NATS |
| 04 | AGENTS | Tri-units |
| 05 | FRAMEWORKS | Hermes runtime |
| 06 | PROCESSES | Pipelines OCR, PDF, video |
| 07 | INTERFACES | Mission Control, Grafana |
| **08** | **KNOWLEDGE** | **Qdrant, Engram, SurrealDB, Compass, Obsidian vault, Git repo** |
| 09 | CONTROL | Prometheus, métricas |

### Mapa de puertos TIER-08

| Puerto | Servicio | Estado |
|:------:|----------|:------:|
| 6333 | Qdrant | ✅ existente |
| 7437 | Engram | ✅ existente |
| 8081 | llama-server (embeddings) | ✅ existente |
| 10801 | RAGFlow (opcional, futuro) | ⏳ |
| 10804 | Obsidian vault (archivos, no servidor) | ✅ existe |
| **10807** | **SurrealDB** | **⏳ instalar** |
| **10808** | **Compass MCP** | **⏳ instalar** |

---

## Coexistencia Raw + Destilado

### Cuándo usar cada ruta

| Necesitas | Ruta raw (RAGFlow/LlamaIndex) | Ruta destilada (JKS) |
|-----------|:----------------------------:|:--------------------:|
| Preguntar al PDF recién bajado | ✅ rápido | ❌ 5-10 min de procesamiento |
| Cita textual exacta | ✅ | ❌ el resumen puede omitirla |
| Forensia: "¿dónde dijo exactamente X?" | ✅ | ⚠️ tenés source.uri + checksum |
| Explorar si un doc vale la pena | ✅ | ❌ mejor preguntar primero |
| Consulta recurrente | ❌ | ✅ ya está en rules/ |
| Navegar conceptos relacionados | ❌ | ✅ wikilinks + grafo |
| Trazabilidad: "¿de dónde salió esto?" | ❌ | ✅ frontmatter con fuente |
| Sin conexión | ❌ | ✅ markdown plano |

### El flujo completo

```
PDF nuevo
    │
    ├──► (opcional) RAGFlow: preguntar ya, mientras se procesa
    │
    └──► ingest.sh: destila en background
           └──► .md en domains/
           └──► Qdrant + SurrealDB + Engram
           └──► disponible en Obsidian + agents
```

No es una disyuntiva. Es las dos, cada una en su momento.

---

## Acceso desde cualquier dispositivo

| Dispositivo | Leer KB | Editar KB | Añadir original |
|-------------|:-------:|:---------:|:---------------:|
| Mac (Workstation) | ✅ Obsidian | ✅ Obsidian | ✅ catalog.csv |
| iPad / Tablet | ✅ Obsidian (Sync) | ✅ Obsidian (Sync) | ⏳ catalog vía editor |
| iPhone | ✅ GitHub web / Obsidian | ⚠️ limitado | ✅ añadir URL raw/catalog.csv |
| Cualquier navegador | ✅ GitHub web | ✅ GitHub web editor | ✅ |
| Sin conexión | ✅ el repo está local | ✅ git commit offline | ✅ |

Obsidian Sync es opcional (pago). Alternativa gratuita: trabajar sobre el repo Git y usar GitHub web desde el móvil.

## Punto de Vista Alternativo: El Repo como Central (no el Mac Mini)

El diseño principal asume que el Mac Mini es el servidor central (TIER-08 con Qdrant, SurrealDB, Compass) y los agents lo consultan siempre. Pero hay escenarios donde eso no funciona: sin red, de viaje, Mac Mini caído.

### Vista alternativa: el repo Git como fuente de verdad única y descentralizada

En esta perspectiva, la central no es ninguna máquina. Es el repositorio Git. Cada dispositivo tiene el repo completo localmente y es autónomo:

```
WORKSTATION (tu Mac)          MÓVIL / TABLET            MAC MINI (servidor)
─────────────────────         ──────────────────        ─────────────────────
Repo completo local           Repo completo (clone)     Repo completo local
Obsidian funciona offline     Editor de texto           Qdrant, SurrealDB
ingest.sh local               Añadir catalog.csv        Compass corriendo
git commit (local)            git commit (local)        Agents consultan
                              ─── sin conexión ───      ─── sin conexión ───
                              No hay servicios          No hay agents
                              Solo editar .md           Pero repo íntegro
                              Añadir líneas al CSV
```

### Escenarios

| Situación | Funciona | No funciona |
|-----------|----------|-------------|
| Casa con red ✅ | TODO: ingest.sh, Obsidian, agents, sync | — |
| Casa sin red | Editar .md, correr ingest.sh, git commit local | Sincronizar, agents consultar |
| De viaje sin Mac Mini | Obsidian + repo completo en laptop | Agents (corren en Mac Mini) |
| De viaje solo móvil | Leer KB, añadir catalog.csv | Ingesta completa (LLM pesado) |
| Mac Mini caído | Editar, ingestar, commit local | Agents no tienen servicios |
| Sin red en ningún lado | Editar + ingestar + commit local | Sincronizar |

### Mobile y tablet

| Dispositivo | Leer KB | Editar .md | Añadir original | Ingesta completa |
|-------------|:-------:|:----------:|:---------------:|:----------------:|
| iPhone | GitHub mobile / Working Copy | Working Copy (editor) | Añadir línea a catalog.csv | No (LLM muy pesado) |
| iPad | Obsidian / Working Copy | Obsidian / Working Copy | Añadir línea a catalog.csv | No (LLM muy pesado) |
| Cualquier navegador | GitHub web | GitHub web editor | GitHub web | No |

**App recomendada para mobile**: Working Copy (iOS) — clona el repo, edita archivos, hace commit y push. Gratuito para uso básico.

### Cuándo elegir esta vista sobre la principal

- Pasás tiempo fuera de casa sin el Mac Mini
- La conectividad a internet es intermitente
- Querés poder ingestar desde cualquier lado (aunque sea solo registrar el original, la destilación viene después)
- El Mac Mini no es 100% fiable como servidor 24/7

### En la práctica, conviven ambas

El diseño principal funciona cuando estás en casa con red y agents activos. Esta vista alternativa cubre los bordes: sin red, de viaje, móvil. El repo es el mismo. Los .md son los mismos. El Git es el mismo. Solo cambia qué máquina está corriendo servicios en cada momento.

## Encriptacion

Sin FileVault (por decision del usuario). La proteccion se maneja a nivel de archivo, no de disco completo.

### Estrategia

| Capa | Proteccion | Detalle |
|------|-----------|---------|
| Disco local (Workstation + Mac Mini) | Ninguna adicional | Se asume entorno controlado. Sesion con contrasena + bloqueo automatico. |
| Transito (Git push/pull) | SSH / HTTPS (TLS) | GitHub usa SSH o HTTPS. Tailscale cifra el trafico entre maquinas. B2 usa HTTPS. |
| Remoto (GitHub, B2) | git-crypt | Cifrado selectivo por archivo en el repositorio remoto. |

### git-crypt: cifrado selectivo

No se cifra todo el repositorio. Solo las carpetas que contienen datos personales o sensibles:

```gitattributes
# ~/knowledge/.gitattributes
domains/personal/**     filter=git-crypt diff=git-crypt
secrets/**              filter=git-crypt diff=git-crypt

# El resto viaja sin cifrar
domains/ia/**           !filter
domains/infra/**        !filter
domains/dev/**          !filter
domains/audio-music/**  !filter
decisions/**            !filter
rules/**                !filter
procedures/**           !filter
patterns/**             !filter
specs/**                !filter
templates/**            !filter
raw/catalog.csv         !filter
```

### Como queda cada carpeta

| Carpeta | En local (tu Mac) | En GitHub / B2 | 
|---------|:-----------------:|:--------------:|
| domains/ia/ | Legible | Legible |
| domains/infra/ | Legible | Legible |
| domains/dev/ | Legible | Legible |
| domains/audio-music/ | Legible | Legible |
| decisions/, rules/, procedures/... | Legible | Legible |
| **domains/personal/** | **Legible** | **Cifrado** |
| **secrets/** | **Legible** | **Cifrado** |

En local, git-crypt es transparente: los archivos se ven descifrados. En el remoto (GitHub, B2), los archivos marcados se almacenan cifrados y solo quien tenga la clave GPG puede descifrarlos.

### Alternativa sin GitHub

Si no se quiere exponer nada en GitHub, se elimina el remote origin y se usan solo:

- **Mac Mini** como remote primario (acceso solo por Tailscale, solo tu usuario)
- **B2 / S3** como backup cifrado (solo tu clave GPG puede descifrar)

En ese caso, `.gitattributes` puede omitirse porque no hay remoto no-confiable.

### Consideraciones

- La clave GPG de git-crypt debe estar respaldada (por ejemplo, en 1Password). Si se pierde, los archivos cifrados en remoto son irrecuperables.
- El cifrado aplica solo al repositorio remoto. En local los archivos están siempre descifrados (git-crypt lo hace transparente).
- No hay cifrado en reposo en disco local por decision del usuario. Si en el futuro cambia la necesidad, FileVault sigue siendo opcion.
