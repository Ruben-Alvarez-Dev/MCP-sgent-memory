"""Deterministic query intent classifier.

The program runs with ZERO local generation models: this module only hosts
the deterministic intent classifier used by retrieval routing.

Usage:
    from shared.llm import classify_intent

    intent = classify_intent(query)    # clasificador determinista (<5ms)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Query Intent Classifier (determinista, <5ms) ──────────────────

@dataclass
class QueryIntent:
    """Classified intent of a user/LLM query."""
    intent_type: str          # code_lookup | decision_recall | how_to |
                               # relationship | summary | conversation_recall |
                               # error_diagnosis | pattern_match
    entities: list[str]       # ["AuthService", "JWT", "user_session"]
    scope: str                # this_project | general | user_preference
    time_window: str          # now | recent | historical | all
    needs_external: bool      # necesita Context7 / docs externos
    needs_ranking: bool       # necesita AI ranking de memorias
    needs_consolidation: bool # necesita consolidación post-sesión


def classify_intent(
    query: str,
    session_type: str = "coding",
    open_files: list[str] | None = None,
) -> QueryIntent:
    """Classify query intent using heuristics — no LLM needed.

    Args:
        query: The user/LLM query text.
        session_type: Current session type (coding, voice_chat, etc.)
        open_files: Currently open files in the IDE.

    Returns:
        QueryIntent with classified intent.
    """
    intent = QueryIntent(
        intent_type="pattern_match",
        entities=[],
        scope="this_project" if session_type == "coding" else "general",
        time_window="all",
        needs_external=False,
        needs_ranking=False,
        needs_consolidation=False,
    )
    q = query.lower()
    open_files = open_files or []

    # Intent type detection
    if any(kw in q for kw in ["why did we", "why do we use", "why not",
                               "we decided", "decision", "decisions",
                               "rationale", "choice",
                               "decidimos", "decisión",
                               "decisiones", "decidir", "elegimos",
                               "cambiamos", "qué decidimos",
                               "por qué usamos", "acuerdo", "motivo",
                               "razón"]):
        intent.intent_type = "decision_recall"
        intent.time_window = "historical"
        intent.needs_ranking = True

    elif any(kw in q for kw in ["how to", "how do i", "cómo", "de qué manera",
                                 "what's the best way", "cómo hago"]):
        intent.intent_type = "how_to"
        intent.needs_external = True
        intent.needs_ranking = True

    elif any(kw in q for kw in ["function", "class", "method", "import", "file",
                                 "función", "archivo", "módulo"]):
        if any(kw in q for kw in ["does", "what is", "where is", "show me",
                                   "hace", "dónde está", "mostrame"]):
            intent.intent_type = "code_lookup"
            intent.needs_ranking = True

    elif any(kw in q for kw in ["related", "depends on", "conecta",
                                 "relación", "cómo se relaciona", "depende"]):
        intent.intent_type = "relationship"
        intent.needs_ranking = True

    elif any(kw in q for kw in ["summarize", "resumen", "overview",
                                 "what's happening", "qué está pasando",
                                 "resumí"]):
        intent.intent_type = "summary"
        intent.time_window = "recent"

    elif any(kw in q for kw in ["we said", "dijimos", "before", "antes",
                                 "earlier", "lo que habl", "mencionamos"]):
        intent.intent_type = "conversation_recall"
        intent.time_window = "recent"

    elif any(kw in q for kw in ["error", "bug", "fallo", "crash",
                                 "not working", "doesn't work", "broken",
                                 "roto", "falla"]):
        intent.intent_type = "error_diagnosis"
        intent.needs_external = True
        intent.time_window = "recent"

    # Entity extraction (CamelCase, UPPER_SNAKE, UPPER_SNAKE_DIGITS)
    camel_matches = re.findall(r'[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*', query)
    # Digits included so FTS5, ports (6333), etc. are captured whole
    snake_matches = re.findall(r'[A-Z_0-9]{2,}', query)
    # M3: sorted() — list(set(...)) varied with PYTHONHASHSEED per process,
    # making the embedded query text (and retrieval) non-reproducible.
    code_entities = sorted(set(camel_matches + snake_matches))

    # Fallback: keyword extraction for natural language queries (español, english)
    if not code_entities:
        STOP_WORDS = {
            # English
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was", "were",
            "how", "what", "why", "when", "where", "who", "which",
            "do", "does", "did", "will", "would", "could", "should",
            "not", "this", "that", "these", "those", "has", "have", "had",
            "can", "about", "into", "over", "after", "before",
            # Español
            "el", "la", "los", "las", "un", "una", "de", "del", "que",
            "y", "o", "pero", "con", "sin", "para", "por", "se", "su",
            "como", "muy", "es", "son", "tiene", "este", "esta",
            "no", "si", "mi", "tu", "lo", "le", "me", "te", "nos",
            "fue", "ser", "hay", "mas", "tambien", "todo", "todos",
        }
        # Alphanumeric tokens; pure digits only valid at 4+ chars,
        # 3-char tokens must contain letters (ports like "808" stay out).
        tokens = re.findall(r'[a-záéíóúüñA-Z0-9_]{3,}', q)
        code_entities = [
            t for t in tokens
            if t not in STOP_WORDS and (len(t) >= 4 or not t.isdigit())
        ][:10]

    intent.entities = code_entities

    # Open files affinity
    for f in open_files:
        fname = f.rsplit("/", 1)[-1] if "/" in f else f
        if fname.lower() in q or fname.rsplit(".", 1)[0].lower() in q:
            if fname not in intent.entities:
                intent.entities.append(fname)

    # Session type adjustments
    if session_type == "voice_chat":
        intent.time_window = "recent"
        intent.scope = "user_preference"
    elif session_type == "coding":
        intent.scope = "this_project"

    return intent
