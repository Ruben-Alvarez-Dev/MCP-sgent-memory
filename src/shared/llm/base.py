"""LLM Backend abstraction — provider-agnostic interface.

All LLM-consuming code in the memory server uses ONLY this interface.
The backend (llama.cpp) is fully hidden.

Usage:
    from shared.llm import get_llm

    llm = get_llm()  # auto-selects configured backend
    response = llm.chat([{"role": "user", "content": "hello"}])

    for chunk in llm.stream(messages):
        print(chunk.delta, end="")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Generator


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str          # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ChatResponse:
    """Complete chat response."""
    content: str
    model: str
    finish_reason: str | None = None
    usage: dict | None = None  # {input_tokens, output_tokens, total_tokens}


@dataclass
class ChatChunk:
    """A streaming chunk from the model."""
    delta: str
    model: str
    finish_reason: str | None = None


class ModelInfo:
    """Information about the loaded model."""

    def __init__(
        self,
        name: str,
        max_context: int,
        backend: str,
        capabilities: list[str] | None = None,
    ):
        self.name = name
        self.max_context = max_context
        self.backend = backend
        self.capabilities = capabilities or ["chat", "stream"]


class LLMBackend(ABC):
    """Abstract LLM backend.

    All implementations must provide chat() and stream().
    The rest of the system NEVER knows which backend is active.
    """

    # ── Lifecycle ─────────────────────────────────────────────────

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend can run in the current environment.

        Should be fast — no network calls, just local checks.
        """
        ...

    @abstractmethod
    def model_info(self) -> ModelInfo:
        """Return information about the currently loaded model."""
        ...

    # ── Chat (non-streaming) ──────────────────────────────────────

    @abstractmethod
    def chat(
        self,
        messages: list[dict] | list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ChatResponse:
        """Send messages and get a complete response.

        Args:
            messages: Conversation history in OpenAI format.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens to generate.
            stop: Stop sequences.
            tools: Tool schemas for function calling.
            tool_choice: Tool selection strategy.

        Returns:
            ChatResponse with the full generated content.
        """
        ...

    # ── Streaming ─────────────────────────────────────────────────

    @abstractmethod
    def stream(
        self,
        messages: list[dict] | list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> Generator[ChatChunk, None, None]:
        """Stream the response token by token.

        Yields ChatChunk objects as they arrive from the model.
        """
        ...

    # ── Convenience ───────────────────────────────────────────────

    def ask(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Simple Q&A — wraps chat() for single-turn usage.

        Args:
            prompt: User message.
            system: Optional system prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens.

        Returns:
            The assistant's response text.
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return response.content

    def __repr__(self) -> str:
        info = self.model_info() if self.is_available() else None
        if info:
            return f"<{self.__class__.__name__}: {info.name} ({info.backend})>"
        return f"<{self.__class__.__name__}: unavailable>"
