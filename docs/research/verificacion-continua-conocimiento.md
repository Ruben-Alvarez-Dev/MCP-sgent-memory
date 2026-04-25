# Verificación Continua del Conocimiento en Sistemas de Memoria para Agentes de IA

## Documento de Investigación — MCP-agent-memory

**Fecha**: Abril 2026  
**Autoría**: Arquitectura MCP-agent-memory / CLI-agent-memory  
**Estado**: Investigación activa — fase de integración  
**Clasificación**: Interna — desarrollo de roadmap

---

## Resumen

Este documento analiza el problema de la **obsolescencia del conocimiento** en sistemas de memoria persistente para agentes de IA. Cuando un agente almacena información sobre un proyecto, repositorio o decisión arquitectónica, esa información tiene una vida útil limitada. Los archivos cambian, las decisiones se revierten, los repositorios se reestructuran. Si el agente opera con datos obsoletos sin verificarlos, toma decisiones erróneas con confianza inmerecida.

La investigación se estructura en tres ejes: (1) los mecanismos que el cerebro humano utiliza para mantener la confiabilidad de sus recuerdos, (2) las técnicas SOTA (State of the Art) en la comunidad de IA para abordar este problema, y (3) una propuesta algorítmica concreta que integra ambos enfoques en el sistema MCP-agent-memory.

**Conclusión principal**: El proceso óptimo no es verificar todo constantemente, sino aplicar **verificación selectiva basada en relevancia, confianza y velocidad de cambio** — exactamente como hace el cerebro. El acto mismo de recordar debe ser una oportunidad de verificación (reconsolidación), no un simple proceso de lectura.

---

## 1. Introducción — El Problema

### 1.1 Definición del problema

Un sistema de memoria para agentes de IA enfrenta una tensión fundamental:

- **Necesita recordar** para operar con contexto y coherencia.
- **No puede confiar ciegamente** en lo que recuerda porque la realidad cambia.
- **No puede verificar todo** porque el costo computacional y temporal sería prohibitivo.

Este problema se manifiesta en nuestro sistema MCP-agent-memory de forma concreta: tenemos 53 herramientas MCP, vk-cache inyecta contexto automáticamente en cada turno, y autodream consolida memories periódicamente. Pero **ningún mecanismo verifica que lo almacenado siga siendo cierto**.

### 1.2 Ejemplo concreto

El sistema almacena: *"CLI-agent-memory está en `/tmp/CLI-agent-memory/`"* (confidence 0.74).

La realidad al momento de consultar: CLI-agent-memory está en `~/CLI-agent-memory/`, tiene tags hasta v1.0.0, y tiene una estructura `adapters/` que no existía cuando se almacenó ese dato.

Si el agente opera con el dato viejo sin verificar, sus acciones serán incorrectas. No es un problema teórico — sucedió en esta misma sesión.

### 1.3 Alcance de la investigación

Este documento investiga:
- Cómo el cerebro humano resuelve este problema (Sección 3)
- Qué técnicas ha desarrollado la comunidad de IA (Sección 4)
- Qué propuesta algorítmica concreta implementamos (Sección 5)
- Cómo se integra en el roadmap del sistema (Sección 6)

---

## 2. Metodología

### 2.1 Enfoque

Revisión narrativa estructurada con análisis comparativo. No es una revisión sistemática formal (no aplicamos criterios PRISMA), sino una síntesis dirigida de la literatura relevante para fundamentar una decisión arquitectónica.

### 2.2 Fuentes

- Literatura primaria: papers de neurciencia cognitiva y NLP/IR (1990–2026)
- Implementaciones de referencia: Self-RAG, CRAG, HippoRAG, FreshQA
- Arquitectura del sistema: código fuente de MCP-agent-memory y CLI-agent-memory

---

## 3. Marco Teórico — Neurociencia de la Memoria Verificable

### 3.1 Reconsolidación de memorias (Nader, 2000; Przybyslawski & Sara, 1997)

**Hallazgo central**: Cuando el cerebro accede a un recuerdo a largo plazo, ese recuerdo se vuelve temporalmente lábil (inestable, modificable) antes de ser re-almacenado. Este proceso se llama **reconsolidación**.

**Implicación para IA**: El acto de RECUPERAR una memoria no debería ser una operación de solo lectura. Debería ser una oportunidad de verificación y actualización. Cada vez que vk-cache recupera contexto, está accediendo a memories que podrían estar obsoletas. El sistema debería aprovechar ese acceso para verificar.

**Evidencia experimental**: Nader (2000) demostró que ratas a las que se les administraba un inhibidor de síntesis proteica inmediatamente después de reactivar un recuerdo de miedo perdían ese recuerdo permanentemente. Esto prueba que la reconsolidación es un proceso activo de re-escritura, no una simple re-lectura.

**Crítica**: La reconsolidación en humanos es más matizada que en modelos animales. Algunos estudios (Chan et al., 2009) sugieren que no todos los recuerdos se reconsolidan cada vez que se accede a ellos — la reconsolidación parece estar gated por factores como la predicción de error y la novedad.

### 3.2 Predictive Coding y Minimización de Error de Predicción (Friston, 2010)

**Hallazgo central**: El cerebro opera como una máquina de predicción. Genera predicciones constantemente, las compara contra la realidad, y actualiza su modelo interno cuando detecta errores de predicción (*prediction errors*). Este marco se conoce como **Predictive Coding** o **Free Energy Principle**.

**Implicación para IA**: El sistema de memoria debería generar predicciones basadas en lo que sabe y compararlas contra el estado actual. Si el archivo que recuerdo tenía 100 líneas ahora tiene 200, hay un error de predicción — y eso debería triggering una actualización.

**Principio algorítmico derivado**: La verificación no necesita ser exhaustiva. Solo necesita ocurrir cuando hay **potencial de sorpresa** — es decir, cuando la realidad podría diferir significativamente de lo almacenado.

### 3.3 Metamemoria — Monitoreo del Propio Conocimiento (Nelson & Narens, 1990)

**Hallazgo central**: El cerebro tiene un sistema de **metamemoria** — la capacidad de monitorear y controlar sus propios procesos de memoria. Esto incluye:
- Saber **qué** sabés (y qué no)
- Saber **qué tan seguro** estás de cada recuerdo
- Saber **cuándo** un recuerdo necesita verificación
- Decidir **cuánto esfuerzo** invertir en recuperar o verificar

**Implicación para IA**: Nuestro sistema ya tiene `confidence` en MemoryItem, pero es un valor estático que se asigna en el momento de almacenamiento y nunca se actualiza. La metamemoria requiere que ese valor sea **dinámico** — se ajuste con cada verificación, acceso fallido, o paso del tiempo.

**Modelo de Nelson & Narens**: El modelo propone dos niveles:
1. **Nivel objeto**: las memorias mismas
2. **Nivel meta**: el monitoreo y control de esas memorias

En nuestro sistema, el nivel objeto son los datos en Qdrant. El nivel meta aún no existe formalmente — necesitamos un sistema que monitorice la confiabilidad de las memories y decida cuándo verificar.

### 3.4 Curva del Olvido y Repetición Espaciada (Ebbinghaus, 1885; Wozniak, 1985)

**Hallazgo central**: Las memorias decaen exponencialmente con el tiempo a menos que sean reforzadas. La repetición espaciada (*spaced repetition*) programa refuerzos en intervalos crecientes justo antes de que el olvido sea significativo.

**Algoritmos modernos**: SM-2 (SuperMemo, 1987), FSRS (Anki, 2023) — calculan el intervalo óptimo de repaso basándose en la dificultad del ítem y el historial de respuestas del usuario.

**Implicación para IA**: Cada tipo de dato tiene una "velocidad de decaimiento" diferente:
- `2 + 2 = 4` → nunca decae (never-changing)
- `"Milei es presidente"` → decae en años (slow-changing)
- `"el archivo X tiene la función Y"` → decae en horas/días (fast-changing)
- `"el servidor está corriendo"` → decae en minutos (real-time)

El sistema debería aplicar intervalos de verificación diferentes según la categoría del dato, no un intervalo uniforme para todo.

### 3.5 Monitoreo de Fuente (Johnson, Hashtroudi & Lindsay, 1993)

**Hallazgo central**: El cerebro no solo almacena recuerdos sino que etiqueta su **origen** (source monitoring): ¿lo vi directamente? ¿me lo dijeron? ¿lo inferí? ¿lo soñé? Esta atribución de fuente es crítica para la confiabilidad.

**Implicación para IA**: Nuestras memories deberían tener un campo `verification_source` que indique cómo se verificó por última vez:
- `direct_observation` — el agente lo verificó leyendo el archivo/repos directamente
- `user_assertion` — el usuario lo dijo, sin verificación independiente
- `inference` — el agente lo dedujo de otros datos
- `unverified` — nunca se verificó contra fuente de verdad

Un dato verificado por observación directa tiene más peso que uno inferido o no verificado.

### 3.6 Síntesis neurocientífica

El cerebro humano maneja la confiabilidad del conocimiento con un proceso de **5 fases** que es selectivo, no-bloqueante, y adaptativo:

```
RECALL → PREDICT → VERIFY → UPDATE → CONSOLIDATE
```

Principios clave:
1. **Selectividad**: No verifica todo. Prioriza por relevancia, confianza, y riesgo.
2. **No-bloqueante**: Usa la información disponible mientras verifica en paralelo.
3. **Categorización**: Clasifica hechos por velocidad de cambio y ajusta la frecuencia de verificación.
4. **Reconsolidación**: Cada acceso es una oportunidad de actualización.
5. **Metamemoria**: Monitoreo continuo del nivel de certeza de cada conocimiento.

---

## 4. Estado del Arte — Técnicas en IA

### 4.1 Evolución del paradigma RAG

El paradigma Retrieval-Augmented Generation (Lewis et al., 2020) resolvió el problema de **acceso** a conocimiento externo, pero introdujo el problema de **calidad** de lo recuperado. La evolución desde RAG hasta las técnicas actuales refleja una progresión clara:

```
RAG (2020)         → Recupera documentos, inyecta al prompt. Sin verificación.
CRAG (2024)        → Evalúa calidad de recuperación. Acciones correctivas si es pobre.
Self-RAG (2023)    → El modelo decide cuándo recuperar, criticar, generar.
FreshQA (2023)     → Clasifica hechos por velocidad de cambio. Verifica según categoría.
HippoRAG (2024)    → Grafo de conocimiento como índice hippocampal.
MemoRAG (2024)     → Memoria como puente entre consulta y respuesta.
MemoryLLM (2024)   → Memoria autoactualizable dentro del modelo.
```

### 4.2 Corrective RAG — CRAG (Yan et al., 2024)

**Principio**: Un evaluador ligero analiza la calidad de los documentos recuperados y devuelve un grado de confianza. Según ese grado, se triggeringan diferentes acciones:

- **Confianza alta**: Usar los documentos directamente.
- **Confianza media**: Refinar con búsqueda web adicional.
- **Confianza baja**: Descartar y buscar completamente de nuevo.

**Algoritmo clave**: `decompose-then-recompose` — descompone los documentos recuperados en unidades de información, filtra las irrelevantes, y recompone solo las relevantes.

**Aplicación a nuestro sistema**: vk-cache ya hace smart_retrieve con scoring por confianza. Pero no tiene la fase de **evaluación post-recuperación**. Cuando inyectamos contexto, nunca nos preguntamos: *"¿estos datos siguen siendo válidos?"*

### 4.3 Self-RAG — Self-Reflective RAG (Asai et al., 2023)

**Principio**: El modelo aprende a generar tokens de reflexión (*reflection tokens*) que le permiten:
- Decidir si necesita recuperar información (`retrieve`)
- Evaluar si la recuperación fue relevante (`is_relevant`)
- Evaluar si su generación está soportada por la recuperación (`is_supported`)
- Evaluar si la respuesta es útil (`is_useful`)

**Innovación**: El modelo no recupera siempre — recupera **bajo demanda** cuando detecta que lo necesita.

**Aplicación a nuestro sistema**: Nuestro v1.3 inyecta contexto automáticamente en cada turno (como RAG clásico). Self-RAG sugiere que sería más eficiente recuperar solo cuando el agente detecta incertidumbre. Sin embargo, para un sistema con contexto automático como el nuestro, la recuperación proactiva es preferible — la mejora vendría de la **fase de crítica** post-recuperación.

### 4.4 FreshQA — Freshness-Aware QA (Vu et al., 2023)

**Principio**: Clasifica las preguntas (y sus respuestas) en tres categorías de frescura:

| Categoría | Ejemplo | Frecuencia de verificación |
|---|---|---|
| **Never-changing** | "¿Cuánto es 2+2?" | Nunca |
| **Slow-changing** | "¿Quién es presidente de Argentina?" | Mensual/anual |
| **Fast-changing** | "¿Qué versión de Python usa este proyecto?" | Cada uso |

**Hallazgo clave**: Los LLMs tienden a responder preguntas fast-changing con datos obsoletos con la misma confianza que datos never-changing. No discriminan entre tipos de hechos.

**Aplicación a nuestro sistema**: Cada MemoryItem debería tener un campo `change_speed` (`never` | `slow` | `fast` | `realtime`) que determine la frecuencia de verificación. Un dato sobre la ubicación de un repo es slow-changing. Un dato sobre el contenido de un archivo es fast-changing.

### 4.5 HippoRAG (2024)

**Principio**: Replica el sistema hippocampal de indexación del cerebro. El hipocampo no almacena los recuerdos completos — almacena **índices** que apuntan a la ubicación de los recuerdos completos en la neocorteza.

**Implementación**: Usa un Knowledge Graph como índice hippocampal. Los nodos son entidades/conceptos. Las aristas son relaciones. Cuando se recupera información, se recorre el grafo desde los nodos relevantes hasta encontrar los pasajes completos.

**Aplicación a nuestro sistema**: Nuestro sistema usa Qdrant (búsqueda vectorial) como mecanismo de recuperación primario. Esto es más como la neocorteza que como el hipocampo. Un grafo de entidades encima de Qdrant mejoraría la recuperación relacional.

### 4.6 Comparativa de enfoques

| Técnica | Resuelve | No resuelve | Complejidad |
|---|---|---|---|
| RAG básico | Acceso a conocimiento externo | Obsolescencia, calidad | Baja |
| CRAG | Calidad post-recuperación | Frescura temporal | Media |
| Self-RAG | Cuándo y cuánto recuperar | Verificación contra fuente | Media-alta |
| FreshQA | Clasificación por frescura | Verificación automática | Media |
| HippoRAG | Recuperación relacional | Veracidad de las relaciones | Alta |

**Conclusión**: Ninguna técnica individual resuelve el problema completo. Se necesita una **combinación** de CRAG (evaluación), FreshQA (clasificación temporal), y verificación contra fuente de verdad.

---

## 5. Propuesta Algorítmica — Verificación Continua del Conocimiento

### 5.1 Principios de diseño

Basados en la neurociencia (Sección 3) y el estado del arte (Sección 4), los principios son:

1. **Memory-first**: Siempre consultar memoria primero. No asumir, no ignorar.
2. **Verificación selectiva**: Solo verificar lo relevante para la acción actual.
3. **No-bloqueante**: El agente procede con lo que tiene. La verificación corre en background.
4. **Categorización temporal**: Cada tipo de dato tiene su velocidad de cambio y frecuencia de verificación.
5. **Reconsolidación**: Cada acceso a una memory es una oportunidad de actualización.
6. **Metamemoria dinámica**: Los scores de confianza se actualizan con cada verificación.

### 5.2 Modelo de datos extendido

El campo `MemoryItem` existente necesita extensiones:

```python
class VerificationStatus(str, Enum):
    NEVER_VERIFIED = "never_verified"     # Nunca se verificó contra fuente de verdad
    VERIFIED = "verified"                 # Verificado recientemente
    STALE = "stale"                       # Verificado pero hace demasiado tiempo
    DISPUTED = "disputed"                 # Verificación falló — dato posiblemente incorrecto

class ChangeSpeed(str, Enum):
    NEVER = "never"       # 2+2=4 — nunca verifica
    SLOW = "slow"         # Decisiones, arquitectura — verifica mensual
    MEDIUM = "medium"     # Estado de repos, estructura — verifica semanal
    FAST = "fast"         # Contenido de archivos — verifica por uso
    REALTIME = "realtime" # Servidor corriendo — verifica siempre

class MemoryItem(BaseModel):
    # ... campos existentes ...
    verified_at: Optional[str] = None           # Última verificación contra fuente de verdad
    verification_source: Optional[str] = None    # Cómo se verificó (file_read, git_log, web, user)
    verification_status: VerificationStatus = VerificationStatus.NEVER_VERIFIED
    change_speed: ChangeSpeed = ChangeSpeed.MEDIUM  # Frecuencia de verificación esperada
    last_accessed_at: Optional[str] = None       # Último acceso (para reconsolidación)
    access_count: int = 0                         # Veces accedido (para priorización)
```

### 5.3 Freshness Score

El freshness score combina confianza, edad, y velocidad de cambio:

```python
def freshness_score(memory: MemoryItem) -> float:
    """Calcula la 'frescura' de una memoria. 1.0 = perfecta, 0.0 = completamente stale."""
    
    base = memory.confidence  # 0.0 - 1.0
    
    # Si nunca se verificó, reducir significativamente
    if memory.verification_status == VerificationStatus.NEVER_VERIFIED:
        return base * 0.5
    
    # Si está disputada, reducir drásticamente
    if memory.verification_status == VerificationStatus.DISPUTED:
        return base * 0.2
    
    # Si está verificada, calcular decaimiento temporal
    if memory.verified_at:
        age_hours = (now() - parse(memory.verified_at)).total_seconds() / 3600
        
        # Half-life según velocidad de cambio (horas hasta que la confianza cae a la mitad)
        half_lives = {
            ChangeSpeed.NEVER:    float('inf'),  # Nunca decae
            ChangeSpeed.SLOW:     720,            # 30 días
            ChangeSpeed.MEDIUM:   168,            # 7 días
            ChangeSpeed.FAST:     24,             # 1 día
            ChangeSpeed.REALTIME: 0.5,            # 30 minutos
        }
        
        half_life = half_lives[memory.change_speed]
        if half_life == float('inf'):
            return base  # Nunca decae
        
        decay = 2 ** (-age_hours / half_life)  # Decay exponencial (modelo Ebbinghaus)
        return base * decay
    
    return base * 0.4  # STALE sin verified_at reciente
```

### 5.4 Pipeline de verificación continua

El proceso completo tiene 5 fases, mapeadas a la arquitectura existente:

#### FASE 1: RECALL — Recuperación mejorada

**Ubicación**: `vk-cache/smart_retrieve()`  
**Cambio**: Agregar freshness_score al ranking de resultados.

```python
# En smart_retrieve, al ordenar resultados:
# ANTES: ordenar por confidence únicamente
# DESPUÉS: ordenar por freshness_score (confidence × decay temporal)
results.sort(key=lambda r: freshness_score(r), reverse=True)
```

**Impacto**: Las memories verificadas recientemente suben. Las stale bajan. El contexto inyectado prioriza lo fresco.

#### FASE 2: PREDICT — Etiquetado de confianza en el ContextPack

**Ubicación**: `ContextPack.to_injection_text()`  
**Cambio**: Incluir indicadores de frescura en el texto inyectado.

```
ANTES:
[automem] (conf=0.75): CLI-agent-memory está en /tmp/CLI-agent-memory

DESPUÉS:
[automem] (conf=0.75, ✅ VERIFIED 2h ago): CLI-agent-memory está en ~/CLI-agent-memory
[automem] (conf=0.80, ⚠️ STALE 5d ago): El proyecto usa ollama para embeddings
[automem] (conf=0.70, ❓ NEVER VERIFIED): El adapter opencode está en el MCP repo
```

**Impacto**: El agente ve qué datos son confiables y cuáles necesitan verificación. Puede priorizar sus acciones en consecuencia.

#### FASE 3: VERIFY — Verificación selectiva en background

**Ubicación**: Nuevo endpoint `/api/verify-memories` + `session.idle` hook  
**Trigger**: Durante idle time, después de cada acción significativa, o cuando el agente lo solicite.

```python
async def verify_memories(session_id: str, memory_ids: list[str]) -> list[VerificationResult]:
    results = []
    for mid in memory_ids:
        memory = await fetch_memory(mid)
        
        # Generar query de verificación según tipo
        if memory.change_speed == ChangeSpeed.FAST:
            # Verificar contra filesystem
            if memory.scope_type == MemoryScope.DOMAIN:
                actual = read_file_or_repo(memory.content)
                match = compare(memory.content, actual)
        
        elif memory.change_speed == ChangeSpeed.SLOW:
            # Verificar contra docs/git
            if memory.type == MemoryType.DECISION:
                actual = check_decision_still_valid(memory)
                match = compare(memory.content, actual)
        
        # Actualizar memory según resultado
        if match:
            memory.verification_status = VerificationStatus.VERIFIED
            memory.verified_at = now()
            memory.confidence = min(1.0, memory.confidence + 0.05)  # Refuerzo
        else:
            memory.verification_status = VerificationStatus.DISPUTED
            memory.confidence = max(0.0, memory.confidence - 0.2)   # Penalización
        
        results.append(VerificationResult(memory_id=mid, status=memory.verification_status))
    return results
```

#### FASE 4: ACT — Actuación con conocimiento etiquetado

**Ubicación**: Agente (LLM)  
**Cambio**: El agente recibe contexto con tags de frescura y puede tomar decisiones informadas sobre qué confiar.

Comportamiento esperado:
- **VERIFIED**: Usar directamente como fuente confiable.
- **STALE**: Usar pero verificar si la acción depende críticamente de ello.
- **NEVER VERIFIED**: Verificar antes de usar para decisiones críticas.
- **DISPUTED**: No usar. Buscar información actualizada.

#### FASE 5: CONSOLIDATE — Refuerzo en el dream cycle

**Ubicación**: `autodream` consolidation  
**Cambio**: Integrar verificación en el ciclo de consolidation existente.

```python
# En el dream cycle existente, agregar paso de verificación:
async def dream_cycle():
    # Paso existente: consolidación de memories
    await consolidate_memories()
    
    # Nuevo paso: verificar memories stale
    stale_memories = await find_stale_memories(threshold=0.5)
    for memory in stale_memories[:10]:  # Limitar a 10 por ciclo
        await verify_memory(memory)
```

### 5.5 Arquitectura del sistema de verificación

```
                         ┌─────────────────────────────────────────────┐
                         │           AGENTE (LLM)                     │
                         │  Ve contexto con tags de frescura          │
                         │  ✅ VERIFIED  ⚠️ STALE  ❓ UNKNOWN        │
                         └──────────────────┬──────────────────────────┘
                                            │ usa contexto
                         ┌──────────────────▼──────────────────────────┐
                         │         vk-cache (smart_retrieve)           │
                         │  Ordena por freshness_score                 │
                         │  confidence × decay(change_speed, age)     │
                         └──────────────────┬──────────────────────────┘
                                            │ recupera memories
              ┌─────────────────────────────▼─────────────────────────────┐
              │                    Qdrant (vector store)                   │
              │  MemoryItem con: verified_at, verification_status,         │
              │  change_speed, access_count, last_accessed_at              │
              └─────────────────────────────┬─────────────────────────────┘
                                            │
           ┌────────────────────────────────┼────────────────────────────────┐
           │                                │                                │
  ┌────────▼─────────┐        ┌────────────▼──────────┐       ┌────────────▼──────────┐
  │  session.idle     │        │  autodream cycle       │       │  /api/verify-memories  │
  │  hook             │        │  (consolidación +      │       │  (endpoint manual)     │
  │  → verify stale   │        │   verificación)        │       │  → verificar bajo      │
  │  → update status  │        │  → verificar stale     │       │    demanda             │
  └──────────────────┘        └───────────────────────┘       └───────────────────────┘
```

---

## 6. Conclusiones Argumentadas

### 6.1 El problema central

Los sistemas de memoria para agentes de IA que solo almacenan y recuperan información sin verificarla están construyendo **confianza sobre arena**. La confianza de un dato no debería ser estática — debería decaer con el tiempo y reforzarse con la verificación, como ocurre en el cerebro humano.

### 6.2 La solución neurocientífica es la correcta

El cerebro resuelve este problema con elegancia:
- No verifica todo (selectividad)
- No se bloquea verificando (no-bloqueante)
- Adapta la frecuencia al tipo de dato (categorización temporal)
- Usa cada acceso como oportunidad de actualización (reconsolidación)

Argumentamos que este enfoque es superior a la verificación exhaustiva por tres razones:
1. **Eficiencia**: Verificar solo lo relevante reduce el costo computacional en órdenes de magnitud.
2. **Fluidez**: El agente no se queda esperando verificaciones. Actúa con lo que tiene y mejora en background.
3. **Adaptabilidad**: Datos fast-changing se verifican frecuentemente; datos never-changing nunca gastan recursos.

### 6.3 La implementación es incremental

No necesitamos reconstruir el sistema. Las extensiones propuestas se integran en la arquitectura existente:

- `MemoryItem` se extiende con 5 campos nuevos (backward compatible)
- `smart_retrieve` agrega freshness scoring al ranking existente
- `ContextPack.to_injection_text()` agrega tags visuales
- `autodream` agrega un paso de verificación al ciclo existente
- Nuevo endpoint `/api/verify-memories` para verificación bajo demanda

### 6.4 La validación empírica es necesaria

Este documento presenta una propuesta fundamentada, no una solución validada. Los próximos pasos incluyen:
1. Implementar el modelo de datos extendido
2. Medir el impacto del freshness scoring en la calidad del contexto recuperado
3. A/B testing: agente con vs sin tags de frescura
4. Medir la tasa de errores por datos obsoletos antes y después de la verificación

### 6.5 Limitaciones

- **Clasificación automática de change_speed**: Determinar si un dato es fast o slow-changing requiere heurísticas que pueden fallar. Una decisión arquitectónica mal clasificada como fast-changing se verificaría innecesariamente.
- **Costo de verificación**: Verificar contra filesystem/repos/APIs tiene costo. Hay que equilibrar exhaustividad con eficiencia.
- **Falsos negativos**: Una verificación que coincide (MATCH) no garantiza que el dato sea correcto — solo que la verificación parcial no encontró discrepancias.

---

## 7. Referencias

### Neurociencia

1. Nader, K. (2000). *Memory traces unbound*. Trends in Neurosciences, 26(2), 65-72.
2. Nader, K., Schafe, G. E., & Le Doux, J. E. (2000). *Fear memories require protein synthesis in the amygdala for reconsolidation after retrieval*. Nature, 406(6797), 722-726.
3. Przybyslawski, J., & Sara, S. J. (1997). *Reconsolidation of memory after its reactivation*. Behavioural Brain Research, 84(1-2), 241-246.
4. Friston, K. (2010). *The free-energy principle: a unified brain theory?* Nature Reviews Neuroscience, 11(2), 127-138.
5. Nelson, T. O., & Narens, L. (1990). *Metamemory: A theoretical framework and new findings*. The Psychology of Learning and Motivation, 26, 125-173.
6. Ebbinghaus, H. (1885). *Über das Gedächtnis*. Leipzig: Duncker & Humblot.
7. Baddeley, A. D., & Hitch, G. (1974). *Working memory*. The Psychology of Learning and Motivation, 8, 47-89.
8. Johnson, M. K., Hashtroudi, S., & Lindsay, D. S. (1993). *Source monitoring*. Psychological Bulletin, 114(1), 3-28.
9. Stickgold, R., & Walker, M. P. (2013). *Sleep-dependent memory consolidation: a guide for the perplexed*. Nature Reviews Neuroscience, 14(7), 492-502.
10. Chan, T. C., et al. (2009). *Reactivation-induced memory instability: is reconsolidation an epiphenomenon?* Neuroscience, 164(4), 1373-1379.

### Inteligencia Artificial

11. Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
12. Yan, S. Q., Gu, J. C., Zhu, Y., & Ling, Z. H. (2024). *Corrective Retrieval Augmented Generation*. ICML 2024. arXiv:2401.15884.
13. Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. arXiv:2310.11511.
14. Vu, T., et al. (2023). *FreshLLMs: FreshQA, FreshPrompt, FreshRL*. EMNLP 2023.
15. Wozniak, P. A. (1985). *SuperMemo: Optimization of learning*. Technical Report.
16. Graves, A., et al. (2016). *Hybrid computing using a neural network with dynamic external memory*. Nature, 538(7626), 471-476.
17. HippoRAG (2024). *HippoRAG: Retrieval-Augmented Generation with Hippocampal Indexing*.
18. Wang, Y., et al. (2024). *MemoryLLM: Training Large Language Models with Self-Updatable Memory*.

---

## A. Apéndice — Mapeo a la Arquitectura MCP-agent-memory

| Concepto neurocientífico | Componente MCP-agent-memory | Estado |
|---|---|---|
| Working Memory | Context window + ContextPack inyectado | ✅ Implementado (v1.3) |
| L0 Raw Events | `automem.ingest_event` | ✅ Implementado |
| L1 Working Memory | `mem0` + `automem.memorize` | ✅ Implementado |
| L2 Episodic Memory | `conversation-store` + autodream L2 | ✅ Implementado |
| L3 Semantic Memory | `engram` decisions + autodream L3 | ✅ Implementado |
| L4 Consolidated | `autodream` L4 summaries | ✅ Implementado |
| L5 Context Assembly | `vk-cache` smart_retrieve | ✅ Implementado |
| Reconsolidación | verificación post-recuperación | 🔜 Propuesto |
| Metamemoria | freshness_score + verified_at | 🔜 Propuesto |
| Predictive Coding | background verification en session.idle | 🔜 Propuesto |
| Curva del olvido | change_speed + decay temporal | 🔜 Propuesto |
| Source Monitoring | verification_source field | 🔜 Propuesto |
| Hippocampal Index | Knowledge Graph sobre Qdrant | 🔜 Futuro |
