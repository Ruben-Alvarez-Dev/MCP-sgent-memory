"""LLM Backend — llama.cpp server.

Runs llama-server (from llama.cpp) as a local subprocess.
Models are loaded from the project's models/ directory.

This backend is fully self-contained — no external services needed.
The server runs OUTSIDE Docker, on the host machine.

Configuration (env vars):
    LLAMA_SERVER_PORT   — Port for the server (default: 8080)
    LLAMA_MODEL         — Model filename in models/ (default: auto-detect)
    LLAMA_N_CTX         — Context size (default: 4096)
    LLAMA_N_GPU_LAYERS — GPU layers to offload (default: -1 = all)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Generator

from .base import LLMBackend, ModelInfo, ChatResponse, ChatChunk


class LlamaCppBackend(LLMBackend):
    """LLM via llama.cpp server running locally.

    The server is managed automatically:
    - start() launches llama-server as a subprocess
    - is_available() checks if the server responds
    - stop() terminates the server process
    """

    def __init__(
        self,
        port: int | None = None,
        model: str | None = None,
        n_ctx: int | None = None,
        n_gpu_layers: int | None = None,
    ):
        self._port = port or int(os.getenv("LLAMA_SERVER_PORT", "8080"))
        self._model_name = model or os.getenv("LLAMA_MODEL")
        self._n_ctx = n_ctx or int(os.getenv("LLAMA_N_CTX", "4096"))
        self._n_gpu_layers = n_gpu_layers or int(os.getenv("LLAMA_N_GPU_LAYERS", "-1"))

        self._process: subprocess.Popen | None = None
        self._base_url = f"http://127.0.0.1:{self._port}"
        self._model_path: Path | None = None
        self._server_bin: Path | None = None
        self._model_info: ModelInfo | None = None

        # Discover binaries and models
        self._discover()

    # ── Discovery ─────────────────────────────────────────────────

    def _discover(self) -> None:
        """Find llama-server binary and model file."""
        # Find server binary
        self._server_bin = self._find_binary("llama-server")
        if self._server_bin is None:
            # Also try legacy name
            self._server_bin = self._find_binary("llama-server-bin")

        # Find model
        if self._model_name:
            # Explicit model name — search in models/
            models_dir = self._models_dir()
            self._model_path = models_dir / self._model_name
            if not self._model_path.exists():
                # Try with common suffixes
                for suffix in ["", ".gguf", ".Q4_K_M.gguf", ".Q5_K_M.gguf"]:
                    candidate = models_dir / f"{self._model_name}{suffix}"
                    if candidate.exists():
                        self._model_path = candidate
                        break
        else:
            # Auto-detect: look for any .gguf in models/
            self._model_path = self._find_model()

    def _find_binary(self, name: str) -> Path | None:
        """Find server binary in engine/bin/ or PATH."""
        root = self._project_root()
        candidates = [
            root / "engine" / "bin" / name,
            root / "bin" / name,
        ]
        for c in candidates:
            if c.exists():
                return c

        # Check PATH
        found = shutil.which(name)
        if found:
            return Path(found)

        return None

    def _models_dir(self) -> Path:
        """Find models/ directory."""
        return self._project_root() / "models"

    def _project_root(self) -> Path:
        """Find project root (parent of shared/)."""
        return Path(__file__).resolve().parent.parent.parent

    def _find_model(self) -> Path | None:
        """Auto-detect a suitable model file."""
        models_dir = self._models_dir()
        if not models_dir.exists():
            return None

        # Prefer instruction-tuned, quantized models
        for pattern in [
            "*instruct*Q4*.gguf",
            "*instruct*.gguf",
            "*Q4_K_M.gguf",
            "*Q4*.gguf",
            "*.gguf",
        ]:
            matches = list(models_dir.glob(pattern))
            if matches:
                return matches[0]

        return None

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self, timeout: float = 30.0) -> bool:
        """Start the llama-server if not already running.

        Returns True if server is ready, False on failure.
        """
        # Check if already running
        if self.is_available():
            return True

        if not self._server_bin:
            return False
        if not self._model_path or not self._model_path.exists():
            return False

        env = os.environ.copy()
        # Set library path for bundled deps
        lib_dir = self._project_root() / "engine" / "lib"
        if lib_dir.exists():
            env["DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"] = str(lib_dir)

        args = [
            str(self._server_bin),
            "--model", str(self._model_path),
            "--port", str(self._port),
            "--ctx-size", str(self._n_ctx),
            "--n-gpu-layers", str(self._n_gpu_layers),
            "--host", "127.0.0.1",
            "--no-webui",
        ]

        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        # Wait for server to be ready
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ping():
                return True
            if self._process.poll() is not None:
                return False  # Process died
            time.sleep(0.5)

        return False

    def stop(self) -> None:
        """Stop the llama-server process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def is_available(self) -> bool:
        """Check if the server is running and responding."""
        return self._ping()

    def _ping(self) -> bool:
        """Health check — ping the server."""
        try:
            req = urllib.request.Request(f"{self._base_url}/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read())
                    return data.get("status") == "ok"
        except Exception:
            pass
        return False

    def model_info(self) -> ModelInfo:
        """Return model information."""
        if self._model_info:
            return self._model_info

        name = self._model_path.stem if self._model_path else "unknown"
        self._model_info = ModelInfo(
            name=name,
            max_context=self._n_ctx,
            backend="llama_cpp",
            capabilities=["chat", "stream"],
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
        """Non-streaming chat completion via llama.cpp server API."""
        body = self._build_request(messages, temperature, max_tokens, stop, tools, tool_choice)
        body["stream"] = False

        data = self._post("/v1/chat/completions", body)

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")

        return ChatResponse(
            content=content,
            model=data.get("model", "llama-cpp"),
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
        """Streaming chat completion via SSE."""
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
        """Build API request body."""
        body = {
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
        """POST JSON to the server."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())

    def _stream_sse(self, path: str, body: dict) -> Generator[ChatChunk, None, None]:
        """Stream SSE response and yield ChatChunks."""
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=120) as resp:
            buffer = ""
            for line_bytes in resp:
                line = line_bytes.decode("utf-8", errors="replace")
                buffer += line

                # SSE: lines starting with "data: "
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue

                    payload = line[6:]  # strip "data: "
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
                            model=chunk.get("model", "llama-cpp"),
                            finish_reason=finish,
                        )
