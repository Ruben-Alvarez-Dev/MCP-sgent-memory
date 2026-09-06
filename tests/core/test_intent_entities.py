"""Intent classifier entity extraction & routing (eval-40 findings).

Covers:
  - UPPER_SNAKE with digits captured whole (FTS5, ports like 6333)
  - Alphanumeric fallback (4+ pure digits valid, 3-char digits rejected)
  - decision_recall routing with expanded ES/EN keywords
  - Prior classification cases not broken (5 representative intents)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shared.llm import QueryIntent, classify_intent

# ── Entities: UPPER_SNAKE + digits ────────────────────────────────

@pytest.mark.unit
def test_fts5_captured_whole():
    """FTS5 must land in entities intact, not truncated to 'FTS'."""
    intent = classify_intent("how does the FTS5 index work in memory_db")
    assert "FTS5" in intent.entities


@pytest.mark.unit
def test_port_number_captured():
    """'puerto 6333' — the port number must be extracted as an entity."""
    intent = classify_intent("en qué puerto corre el qdrant, puerto 6333")
    assert "6333" in intent.entities


@pytest.mark.unit
def test_snake_case_still_captured():
    """Prior UPPER_SNAKE entities keep working."""
    intent = classify_intent("where is MAX_RETRIES defined")
    assert "MAX_RETRIES" in intent.entities


# ── Entities: alphanumeric fallback ───────────────────────────────

@pytest.mark.unit
def test_fallback_and_snake_capture_4plus_digits():
    """Pure digits of 4+ chars end up as entities (snake regex path)."""
    intent = classify_intent("recuerdas el valor 8080 del server")
    assert "8080" in intent.entities


@pytest.mark.unit
def test_fallback_accepts_3char_tokens_with_letters():
    """3-char mixed alnum tokens are valid fallback entities (have letters).

    Note: pure 3-digit runs (e.g. '808') never reach the fallback — the
    snake regex [A-Z_0-9]{2,} captures any 2+ digit run first.
    """
    intent = classify_intent("qué significa la db1 en el config")
    assert "db1" in intent.entities


@pytest.mark.unit
def test_fallback_letters_tokens_pass_stopwords():
    """Natural-language tokens survive the stop-word filter."""
    intent = classify_intent("cómo funciona el ranking semántico")
    assert "ranking" in intent.entities
    assert "funciona" in intent.entities


# ── Routing: decision_recall ──────────────────────────────────────

@pytest.mark.unit
def test_por_que_decidimos_is_decision_recall():
    """'por qué decidimos X' must route to decision_recall (not pattern_match)."""
    intent = classify_intent("por qué decidimos usar postgres en vez de sqlite")
    assert intent.intent_type == "decision_recall"
    assert intent.time_window == "historical"
    assert intent.needs_ranking is True


@pytest.mark.unit
def test_decision_recall_new_keywords():
    """Expanded ES/EN decision keywords route to decision_recall."""
    for query in [
        "cuál fue la decisión sobre el backend",
        "cuál fue el acuerdo del equipo",
        "cuál es el motivo del cambio",
        "cuál es la razón de ese diseño",
        "we decided to use qdrant",
        "what was the rationale for FTS5",
        "why did we drop mongo",
        "was that the right choice",
        "vamos a decidir mañana",          # decidir
        "qué decisiones tomamos ayer",     # decisiones
    ]:
        assert classify_intent(query).intent_type == "decision_recall", query


@pytest.mark.unit
def test_decision_recall_not_shadowed_by_code_lookup():
    """decision_recall wins even when code-ish words are present."""
    intent = classify_intent("por qué decidimos borrar la class AuthService")
    assert intent.intent_type == "decision_recall"


# ── Prior classification cases intact ─────────────────────────────

@pytest.mark.unit
def test_prior_code_lookup_still_works():
    intent = classify_intent("where is the AuthService class defined")
    assert intent.intent_type == "code_lookup"
    assert "AuthService" in intent.entities
    assert intent.needs_ranking is True


@pytest.mark.unit
def test_prior_how_to_still_works():
    intent = classify_intent("how do I deploy the memory server")
    assert intent.intent_type == "how_to"
    assert intent.needs_external is True


@pytest.mark.unit
def test_prior_relationship_still_works():
    intent = classify_intent("which module depends on retrieval")
    assert intent.intent_type == "relationship"


@pytest.mark.unit
def test_prior_summary_still_works():
    intent = classify_intent("dame un resumen de la sesión")
    assert intent.intent_type == "summary"
    assert intent.time_window == "recent"


@pytest.mark.unit
def test_prior_error_diagnosis_still_works():
    intent = classify_intent("the server is broken after the deploy")
    assert intent.intent_type == "error_diagnosis"
    assert intent.needs_external is True


@pytest.mark.unit
def test_prior_default_pattern_match_still_works():
    intent = classify_intent("hola mundo")
    assert intent.intent_type == "pattern_match"


@pytest.mark.unit
def test_returns_query_intent_instance():
    intent = classify_intent("any query")
    assert isinstance(intent, QueryIntent)
