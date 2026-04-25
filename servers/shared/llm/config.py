"""LLM Backend configuration and factory.

Auto-detects and configures the LLM backend based on environment variables.

Usage:
    from shared.llm import get_llm, get_small_llm, classify_intent

    llm = get_llm()                    # auto-select from env (principal)
    small = get_small_llm()            # micro-LLM para ranking/verificación
    intent = classify_intent(query)    # clasificador determinista (<5ms)

Environment variables:
    LLM_BACKEND   — Backend type: llama_cpp (default: llama_cpp)
    LLM_MODEL     — Model name/identifier (backend-specific meaning)
    SMALL_LLM_MODEL — Micro-LLM model (default: qwen3.5:2b)
    LLAMA_SERVER_PORT — llama.cpp server port (default: 8080)
    LLAMA_MODEL   — llama.cpp model filename
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from .base import LLMBackend


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
                               "decidimos", "elegimos", "cambiamos",
                               "qué decidimos", "por qué usamos"]):
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

    # Entity extraction (CamelCase, UPPER_SNAKE)
    camel_matches = re.findall(r'[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*', query)
    snake_matches = re.findall(r'[A-Z_]{2,}', query)
    code_entities = list(set(camel_matches + snake_matches))

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
        tokens = re.findall(r'[a-záéíóúüñA-Z]{3,}', q)
        code_entities = [t for t in tokens if t not in STOP_WORDS][:10]

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


# ── LLM Backend factory ───────────────────────────────────────────

def get_llm(backend: str | None = None, **kwargs) -> LLMBackend:
    """Get the PRIMARY LLM backend (for consolidation, generation, reasoning).

    Args:
        backend: Force a specific backend ("llama_cpp").
                 If None, auto-detects from LLM_BACKEND env var.
        **kwargs: Additional arguments passed to the backend constructor.

    Returns:
        An initialized LLMBackend instance.
    """
    backend_name = backend or os.getenv("LLM_BACKEND", "llama_cpp")
    backend_name = backend_name.lower().strip()

    if backend_name == "llama_cpp":
        return _get_llama_cpp(**kwargs)
    else:
        raise ValueError(
            f"Unknown LLM backend: {backend_name!r}. "
            f"Only supported: llama_cpp"
        )


def get_small_llm(backend: str | None = None, **kwargs) -> LLMBackend:
    """Get the SMALL LLM backend (for ranking, verification, routing).

    Defaults to a micro-LLM model optimized for speed (qwen3.5:2b).

    Args:
        backend: Force a specific backend. If None, auto-detects.
        **kwargs: Additional arguments (e.g., model="qwen3.5:2b").

    Returns:
        An initialized LLMBackend instance for lightweight tasks.
    """
    backend_name = backend or os.getenv("LLM_BACKEND", "llama_cpp")
    backend_name = backend_name.lower().strip()

    # Default micro-LLM model
    default_model = os.getenv("SMALL_LLM_MODEL", "qwen3.5:2b")
    if "model" not in kwargs:
        kwargs["model"] = default_model

    if backend_name == "llama_cpp":
        return _get_llama_cpp(**kwargs)
    else:
        raise ValueError(
            f"Unknown LLM backend: {backend_name!r}. "
            f"Only supported: llama_cpp"
        )


def _get_llama_cpp(**kwargs) -> LLMBackend:
    """Create llama.cpp backend."""
    from .llama_cpp import LlamaCppBackend

    backend = LlamaCppBackend(**kwargs)

    if not backend._server_bin:
        raise RuntimeError(
            "llama-server binary not found.\n"
            f"  Searched in: {backend._project_root()}/engine/bin/\n"
            "  Place llama-server in engine/bin/ or install it in PATH."
        )

    if not backend._model_path or not backend._model_path.exists():
        raise RuntimeError(
            f"Model not found for llama.cpp.\n"
            f"  Searched in: {backend._models_dir()}/\n"
            "  Place a .gguf model file in models/ or set LLAMA_MODEL env var."
        )

    return backend


def list_available_backends() -> dict[str, bool]:
    """Check which backends are available.

    Returns:
        Dict of backend name -> availability.
    """
    results = {}

    try:
        llama = _get_llama_cpp()
         results["llama_cpp"] = llama.is_available()
    except Exception:
        results["llama_cpp"] = False

    return results


# ── LLM Ranking (SPEC-4.1) ───────────────────────────────────────

def rank_by_relevance(
    query: str,
    items: list[dict],
    top_k: int = 10,
    content_key: str = "content",
) -> list[dict]:
    """Rank items by relevance to query using micro-LLM.

    Uses get_small_llm() for fast ranking (~50-200ms).
    Falls back gracefully if LLM not available.

    Args:
        query: The search query.
        items: List of dicts with at least a 'content' key.
        top_k: Max items to return.
        content_key: Key in items dict that holds the text.

    Returns:
        Items reordered by relevance (most relevant first).
    """
    if len(items) <= top_k:
        return items  # No ranking needed

    try:
        llm = get_small_llm()
        if not llm.is_available():
            return items  # LLM not available, return unranked
    except Exception:
        return items

    # Build ranking prompt
    numbered = []
    for i, item in enumerate(items[:30]):  # Max 30 items to rank
        text = str(item.get(content_key, ""))[:200]
        numbered.append(f"{i + 1}. {text}")

    prompt = (
        f"Rank these items by relevance to: {query}\n\n"
        f"Items:\n{chr(10).join(numbered)}\n\n"
        f"Return ONLY the numbers in order of relevance, comma-separated. "
        f"Example: 3,1,5,2,4"
    )

    try:
        response = llm.ask(prompt, max_tokens=128, temperature=0.0)
        # Parse numbers from response
        nums = re.findall(r'\d+', response.strip())
        indices = [int(n) - 1 for n in nums if 0 < int(n) <= len(items)]

        # Reorder by ranking
        ranked = []
        seen = set()
        for idx in indices:
            if idx not in seen:
                ranked.append(items[idx])
                seen.add(idx)

        # Append any items not ranked
        for i, item in enumerate(items):
            if i not in seen:
                ranked.append(item)

        return ranked[:top_k]
    except Exception:
        return items  # Ranking failed, return unranked
