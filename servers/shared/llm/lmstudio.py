"""LLM Backend — LM Studio (OpenAI-compatible API).

Connects to LM Studio's OpenAI-compatible API.
Works with:
  - Local LM Studio (http://localhost:1234)
  - Remote LM Studio via LM Link (Tailscale tunnel to remote GPU)

Configuration (env vars):
    LMSTUDIO_URL  — LM Studio endpoint (default: http://localhost:1234)
    LMSTUDIO_MODEL — Model identifier (default: auto-detected from /v1/models)
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Generator

from .base import LLMBackend, ModelInfo, ChatResponse, ChatChunk


class LMStudioBackend(LLMBackend):
    """LLM via LM Studio OpenAI-compatible API.

    Works with local LM Studio or remote via LM Link (Tailscale).
    """

    def __init__(
        self,
        url: str | None = None,
        model: str | None = None,
    ):
        self._url = (url or os.getenv("LMSTUDIO_URL", "http://localhost:1234")).rstrip("/")
        self._model = model  # None = auto-detect
        self._model_info: ModelInfo | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if LM Studio is running and serving."""
        try:
            req = urllib.request.Request(f"{self._url}/v1/models")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read())
                models = data.get("data", [])
                return len(models) > 0
        except Exception:
            return False

    def model_info(self) -> ModelInfo:
        """Return model information."""
        if self._model_info:
            return self._model_info

        # Auto-detect if needed
        if not self._model:
            self._model = self._get_loaded_model()

        name = self._model or "unknown"
        max_ctx = 4096  # LM Studio default

        self._model_info = ModelInfo(
            name=name,
            max_context=max_ctx,
            backend="lmstudio",
            capabilities=["chat", "stream"],
        )
        return self._model_info

    def _get_loaded_model(self) -> str | None:
        """Get the currently loaded model from LM Studio."""
        try:
            req = urllib.request.Request(f"{self._url}/v1/models")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = data.get("data", [])
                if models:
                    return models[0].get("id")
        except Exception:
            pass
        return None

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
        """Non-streaming chat via /v1/chat/completions."""
        # Ensure we have a model name
        model = self._model or self._get_loaded_model()
        if not model:
            raise RuntimeError("No model loaded in LM Studio. Load a model first.")

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if stop:
            body["stop"] = stop
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        data = self._post("/v1/chat/completions", body)

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")

        return ChatResponse(
            content=content,
            model=data.get("model", model),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
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
        """Streaming chat via /v1/chat/completions (SSE)."""
        model = self._model or self._get_loaded_model()
        if not model:
            raise RuntimeError("No model loaded in LM Studio. Load a model first.")

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if stop:
            body["stop"] = stop
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice

        yield from self._stream_sse("/v1/chat/completions", body)

    # ── HTTP helpers ──────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        """POST JSON to LM Studio."""
        url = f"{self._url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def _stream_sse(self, path: str, body: dict) -> Generator[ChatChunk, None, None]:
        """Stream SSE response and yield ChatChunks."""
        url = f"{self._url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            buffer = ""
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace")
                buffer += line

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue

                    payload = line[6:]
                    if payload == "[DONE]":
                        return

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    finish = choice.get("finish_reason")

                    if content or finish:
                        yield ChatChunk(
                            delta=content,
                            model=chunk.get("model", "lm-studio"),
                            finish_reason=finish,
                        )
