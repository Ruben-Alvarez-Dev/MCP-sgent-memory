"""LLM module — deterministic query intent classifier only.

Zero local generation models: all LLM-consuming code that remains in this
program is the deterministic intent classifier used by retrieval routing.

    from shared.llm import classify_intent, QueryIntent

    intent = classify_intent(query)          # deterministic classifier (<5ms)
"""

from .config import QueryIntent, classify_intent

__all__ = ["QueryIntent", "classify_intent"]
