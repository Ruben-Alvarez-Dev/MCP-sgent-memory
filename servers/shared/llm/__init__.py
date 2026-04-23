"""LLM Backend — provider-agnostic interface for the memory server.

All LLM-consuming code imports ONLY from this module:

    from shared.llm import get_llm, get_small_llm, classify_intent

The backend (llama.cpp, Ollama, LM Studio) is fully transparent.

Usage:
    llm = get_llm()                          # auto-select configured backend
    small = get_small_llm()                  # micro-LLM for ranking/verification
    intent = classify_intent(query)          # deterministic classifier (<5ms)

    response = llm.ask("What is 2+2?")       # simple Q&A
    response = llm.chat(messages)            # full conversation
    for chunk in llm.stream(messages):       # streaming
        print(chunk.delta, end="")

Environment variables:
    LLM_BACKEND   — llama_cpp | ollama | lmstudio (default: ollama)
    LLM_MODEL     — Model identifier
    SMALL_LLM_MODEL — Micro-LLM model (default: qwen3.5:2b)
    OLLAMA_URL    — Ollama endpoint
    LMSTUDIO_URL  — LM Studio endpoint
"""

from .base import LLMBackend, ChatMessage, ChatResponse, ChatChunk, ModelInfo
from .config import get_llm, get_small_llm, classify_intent, QueryIntent, list_available_backends, rank_by_relevance

__all__ = [
    "LLMBackend",
    "ChatMessage",
    "ChatResponse",
    "ChatChunk",
    "ModelInfo",
    "QueryIntent",
    "get_llm",
    "get_small_llm",
    "classify_intent",
    "list_available_backends",
    "rank_by_relevance",
]
