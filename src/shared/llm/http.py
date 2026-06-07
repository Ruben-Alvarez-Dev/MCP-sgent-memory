"""LLM Backend — HTTP (OpenAI-compatible API).

Connects to any OpenAI-compatible endpoint (llama-swap, Ollama, vLLM, etc.).
No local binaries or .gguf files needed.

Configuration (env vars):
    LLM_SERVER_URL  — Base URL (e.g. http://localhost:9000)
    LLM_MODEL       — Model name as known by the server (e.g. qwen3.5-2b)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Generator

from .base import LLMBackend, ModelInfo, ChatResponse, ChatChunk


class HttpLLMBackend(LLMBackend):
    """LLM via HTTP endpoint (OpenAI-compatible chat/completions API)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._base_url = (base_url or os.getenv("LLM_SERVER_URL", "http://localhost:9000")).rstrip("/")
        self._model = model or os.getenv("LLM_MODEL", "qwen3.5-2b")
        self._available: bool | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            req = urllib.request.Request(f"{self._base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                self._available = resp.status == 200
        except Exception:
            self._available = False
        return self._available

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self._model,
            max_context=4096,
            backend="http",
            capabilities=["chat", "stream"],
        )

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
        body = self._build_request(messages, temperature, max_tokens, stop, tools, tool_choice)
        body["stream"] = False

        data = self._post("/v1/chat/completions", body)

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")

        return ChatResponse(
            content=content,
            model=data.get("model", self._model),
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
        body = self._build_request(messages, temperature, max_tokens, stop, tools, tool_choice)
        body["stream"] = True

        yield from self._stream_sse("/v1/chat/completions", body)

    # ── HTTP helpers ──────────────────────────────────────────────

    def _build_request(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        stop: list[str] | None,
        tools: list[dict] | None,
        tool_choice: str | None,
    ) -> dict:
        body: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            body["stop"] = stop
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
        return body

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def _stream_sse(self, path: str, body: dict) -> Generator[ChatChunk, None, None]:
        url = f"{self._base_url}{path}"
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
                            model=chunk.get("model", self._model),
                            finish_reason=finish,
                        )
