"""LLM Backend — Ollama.

Connects to an Ollama instance (local or remote).
Uses Ollama's native API (/api/chat for chat, /api/generate for completion).

Configuration (env vars):
    OLLAMA_URL   — Ollama endpoint (default: http://localhost:11434)
    OLLAMA_MODEL — Model name (default: qwen2.5:7b)
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Generator

from .base import LLMBackend, ModelInfo, ChatResponse, ChatChunk


class OllamaBackend(LLMBackend):
    """LLM via Ollama API (local or remote)."""

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
    ):
        self._url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self._model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self._model_info: ModelInfo | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if Ollama is running and has our model."""
        try:
            req = urllib.request.Request(f"{self._url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check if our specific model is available
                return any(self._model in m for m in models)
        except Exception:
            return False

    def model_info(self) -> ModelInfo:
        """Return model information."""
        if self._model_info:
            return self._model_info

        # Try to get details from Ollama
        max_ctx = 4096  # default
        try:
            req = urllib.request.Request(
                f"{self._url}/api/show",
                data=json.dumps({"name": self._model}).encode(),
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                params = data.get("parameters", {})
                # Ollama doesn't always expose context length in show
                max_ctx = 4096
        except Exception:
            pass

        self._model_info = ModelInfo(
            name=self._model,
            max_context=max_ctx,
            backend="ollama",
            capabilities=["chat", "stream", "embed"],
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
        """Non-streaming chat via /api/chat."""
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        # Qwen3.x and reasoning models need extra budget for thinking
        if max_tokens < 256:
            body["options"]["num_predict"] = max(max_tokens, 256)
        if stop:
            body["options"]["stop"] = stop

        data = self._post("/api/chat", body)

        message = data.get("message", {})
        content = message.get("content", "")
        # Qwen3.x puts reasoning in 'thinking' field — include it in response
        thinking = message.get("thinking", "")
        if thinking and not content:
            content = thinking

        return ChatResponse(
            content=content,
            model=self._model,
            finish_reason="stop" if not data.get("done", True) else "stop",
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
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
        """Streaming chat via /api/chat (stream=true)."""
        body = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if stop:
            body["options"]["stop"] = stop

        yield from self._stream_ndjson("/api/chat", body)

    # ── HTTP helpers ──────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        """POST JSON to Ollama."""
        url = f"{self._url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def _stream_ndjson(self, path: str, body: dict) -> Generator[ChatChunk, None, None]:
        """Stream NDJSON response from Ollama."""
        url = f"{self._url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = chunk.get("message", {})
                content = message.get("content", "")
                done = chunk.get("done", False)

                if content or done:
                    yield ChatChunk(
                        delta=content,
                        model=self._model,
                        finish_reason="stop" if done else None,
                    )
