"""LLM module — deterministic query intent classifier only.

Zero local generation models: all LLM-consuming code that remains in this
program is the deterministic intent classifier used by retrieval routing.

    from shared.llm import classify_intent, QueryIntent

    intent = classify_intent(query)          # deterministic classifier (<5ms)
"""

from .config import classify_intent, QueryIntent

__all__ = ["classify_intent", "QueryIntent"]
