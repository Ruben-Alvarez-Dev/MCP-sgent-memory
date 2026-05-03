# Vault del Agente de Memoria

## Como crear una nota nueva

1. Crea un archivo en **Inbox/**
2. Escribe tu contenido en espanol
3. Pon **un tag** al inicio para clasificar:

| Tag | Destino | Descripcion |
|-----|---------|-------------|
| #decision | Decisiones/ | Decisiones arquitectonicas, elecciones de diseno |
| #conocimiento | Conocimiento/ | Patrones, lecciones, investigacion |
| #episodio | Episodios/ | Relatos de sesiones, incidentes, eventos |
| #entidad | Entidades/ | Proyectos, personas, herramientas, conceptos |
| #nota | Notas/ | Cualquier otra cosa (por defecto) |

4. Guarda. El sistema hace el resto automaticamente:
   - Renombra al formato L3_KNOWLEDGE_20260503T143000_00001_ES.md
   - Traduce al ingles y crea la version _EN.md
   - Registra timestamp, tags, relaciones
   - Mueve a la carpeta correcta

## Sin tag = va a Notas/

Si no pones ningun tag, la nota va a **Notas/** por defecto.

## Editar una nota existente

Abre la nota en Obsidian, edita, guarda.
El daemon detecta el cambio y sincroniza automaticamente:
- Actualiza version EN si editaste ES
- Actualiza frontmatter (updated timestamp)
- Re-indexa relaciones

## Formato de nombre (automatico, no tocar)

L{capa}_{TIPO}_{YYYYMMDDTHHMMSS}_{NNNNN}_{lang}.md

- capa: L0 (sensorial), L2 (episodico), L3 (semantico), L4 (narrativo), L5 (selectivo)
- tipo: DECISION, KNOWLEDGE, EPISODE, ENTITY, NOTE, INBOX, PERSON, TEMPLATE
- timestamp: fecha y hora de creacion (inmutable)
- secuencia: numero unico de 5 digitos
- idioma: ES (espanol) o EN (ingles)

## Estructura de carpetas

Carpetas en espanol (lo que tu ves):
  Inbox/       ← Crea aqui tus notas nuevas
  Decisiones/  ← #decision
  Conocimiento/ ← #conocimiento
  Episodios/   ← #episodio
  Entidades/   ← #entidad
  Notas/       ← #nota (o sin tag)
  Personas/    ← #persona
  Plantillas/  ← Plantillas reutilizables

Carpetas en ingles (copia automatica del sistema):
  inbox/, decisions/, knowledge/, episodes/, entities/, notes/, people/, templates/

## Relaciones entre notas

El sistema detecta automaticamente notas relacionadas por:
- Misma fecha de creacion
- Tags compartidos
- Contenido similar (via embeddings)
- Wikilinks manuales: [[L3_DECISION_20260503T143000_00001]]

Tu puedes anadir relaciones manuales con wikilinks si quieres.
