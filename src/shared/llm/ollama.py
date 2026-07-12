"""LLM Backend — Ollama server (native API).

Talks to a locally running Ollama daemon using its NATIVE endpoints:
    POST /api/chat       — multi-turn chat (used by chat()/stream())
    POST /api/generate   — single-prompt completion (used by generate())
    GET  /api/tags       — availability + model existence check

Ollama is an external service — this backend never starts/stops it.
See ADR-0004: on machines where llama.cpp Metal is unreliable, Ollama
is the preferred backend; the tier resolver picks it when reachable.

Configuration (env vars):
    OLLAMA_URL   — Base URL of the daemon (default: http://127.0.0.1:11434)
    LLM_MODEL    — Model tag to use (default: qwen2.5:7b)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Generator

import httpx

from .base import (
    ChatChunk,
    ChatResponse,
    LLMBackend,
    LLMModelNotFoundError,
    LLMUnavailableError,
    ModelInfo,
)

logger = logging.getLogger("agent-memory.llm.ollama")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"
AVAILABILITY_TIMEOUT = 2.0   # seconds — /api/tags probe
REQUEST_TIMEOUT = 120.0      # seconds — chat/generate


class OllamaBackend(LLMBackend):
    """LLM via a running Ollama daemon (native /api/chat + /api/generate)."""

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
        num_ctx: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = (url or os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)).rstrip("/")
        self._model_name = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self._num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        # transport is dependency injection for unit tests (httpx.MockTransport);
        # production always uses the default HTTP transport.
        self._transport = transport
        self._model_info: ModelInfo | None = None
        self._model_verified = False

    # ── HTTP helpers ──────────────────────────────────────────────

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=self._transport,
        )

    def _connection_failure(self, exc: Exception) -> LLMUnavailableError:
        """Report the failure to the tier resolver and build a typed error."""
        try:
            from shared import model_tier  # late import — avoids cycles
            model_tier.notify_backend_failure("ollama")
        except ImportError:
            pass  # model_tier not on path (e.g. isolated unit test) — error below still raised
        return LLMUnavailableError(
            f"Ollama unreachable at {self._base_url}: {exc}"
        )

    # ── Lifecycle ─────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check the daemon responds on /api/tags (2s timeout). Never raises."""
        try:
            with self._client(AVAILABILITY_TIMEOUT) as client:
                resp = client.get("/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        """Return model tags known to the daemon via /api/tags."""
        try:
            with self._client(AVAILABILITY_TIMEOUT) as client:
                resp = client.get("/api/tags")
                resp.raise_for_status()
                return [m.get("name", "") for m in resp.json().get("models", [])]
        except httpx.HTTPError as e:
            raise self._connection_failure(e) from e

    def _ensure_model(self) -> None:
        """Verify the configured model exists in /api/tags (once per instance)."""
        if self._model_verified:
            return
        tags = self.list_models()
        wanted = self._model_name
        # "qwen2.5:7b" matches both "qwen2.5:7b" and Ollama's normalized tags
        if not any(t == wanted or t.split(":latest")[0] == wanted for t in tags):
            raise LLMModelNotFoundError(
                f"Model {wanted!r} not found in Ollama tags {tags}. "
                f"Pull it first: ollama pull {wanted}"
            )
        self._model_verified = True

    def model_info(self) -> ModelInfo:
        """Return model information."""
        if self._model_info is None:
            self._model_info = ModelInfo(
                name=self._model_name,
                max_context=self._num_ctx,
                backend="ollama",
                capabilities=["chat", "stream", "generate"],
            )
        return self._model_info

    # ── Chat ──────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ChatResponse:
        """Non-streaming chat via native /api/chat.

        Note: Ollama has no native tool_choice — the argument is accepted for
        interface compatibility and ignored (tools themselves are forwarded).
        """
        body = self._build_request(messages, temperature, max_tokens, stop, tools)
        body["stream"] = False

        data = self._post_json("/api/chat", body, self._model_name)
        message = data.get("message", {})
        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", self._model_name),
            finish_reason=data.get("done_reason"),
            usage=self._usage(data),
        )

    def stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> Generator[ChatChunk, None, None]:
        """Streaming chat via native /api/chat (JSON-lines, not SSE)."""
        body = self._build_request(messages, temperature, max_tokens, stop, tools)
        body["stream"] = True

        self._ensure_model()
        try:
            with self._client(REQUEST_TIMEOUT) as client:
                with client.stream("POST", "/api/chat", json=body) as resp:
                    self._raise_for_status(resp, self._model_name, read_stream=True)
                    for line in resp.iter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Ollama stream: skipping malformed line: %.120s", line)
                            continue
                        delta = chunk.get("message", {}).get("content", "")
                        done = chunk.get("done", False)
                        finish = chunk.get("done_reason") if done else None
                        if delta or done:
                            yield ChatChunk(
                                delta=delta,
                                model=chunk.get("model", self._model_name),
                                finish_reason=finish,
                            )
                        if done:
                            return
        except httpx.TransportError as e:
            raise self._connection_failure(e) from e

    # ── Generate (native single-prompt endpoint) ──────────────────

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> ChatResponse:
        """Single-prompt completion via native /api/generate."""
        body: dict = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "options": self._options(temperature, max_tokens, stop),
        }
        if system:
            body["system"] = system

        data = self._post_json("/api/generate", body, self._model_name)
        return ChatResponse(
            content=data.get("response", ""),
            model=data.get("model", self._model_name),
            finish_reason=data.get("done_reason"),
            usage=self._usage(data),
        )

    # ── Request/response plumbing ─────────────────────────────────

    def _options(
        self, temperature: float, max_tokens: int, stop: list[str] | None
    ) -> dict:
        options: dict = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": self._num_ctx,
        }
        if stop:
            options["stop"] = stop
        return options

    def _build_request(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        stop: list[str] | None,
        tools: list[dict] | None,
    ) -> dict:
        body: dict = {
            "model": self._model_name,
            "messages": messages,
            "options": self._options(temperature, max_tokens, stop),
        }
        if tools:
            body["tools"] = tools
        return body

    def _post_json(self, path: str, body: dict, model: str) -> dict:
        self._ensure_model()
        try:
            with self._client(REQUEST_TIMEOUT) as client:
                resp = client.post(path, json=body)
                self._raise_for_status(resp, model)
                return resp.json()
        except httpx.TransportError as e:
            raise self._connection_failure(e) from e

    def _raise_for_status(
        self, resp: httpx.Response, model: str, read_stream: bool = False
    ) -> None:
        if resp.status_code == 404:
            if read_stream:
                resp.read()
            raise LLMModelNotFoundError(
                f"Ollama returned 404 for model {model!r}: {resp.text[:200]}. "
                f"Pull it first: ollama pull {model}"
            )
        if read_stream and resp.status_code >= 400:
            resp.read()
        resp.raise_for_status()

    @staticmethod
    def _usage(data: dict) -> dict | None:
        input_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")
        if input_tokens is None and output_tokens is None:
            return None
        return {
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0,
            "total_tokens": (input_tokens or 0) + (output_tokens or 0),
        }
