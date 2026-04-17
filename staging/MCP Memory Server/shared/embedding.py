"""Embedding abstraction — agnostic backend system.

Provides a unified interface for generating embeddings with swappable backends:
  - llama_cpp: Bundled llama.cpp binary (default, self-contained)
  - http:       Any HTTP endpoint that returns embeddings (OpenAI, Ollama, etc.)
  - noop:       Returns zero-vectors (testing / fallback)

Configuration is entirely env-driven and project-agnostic:
  EMBEDDING_BACKEND   = llama_cpp | http | noop  (default: llama_cpp)
  EMBEDDING_MODEL     = model path or name (backend-specific)
  EMBEDDING_DIM       = vector dimensionality  (default: 384)
  EMBEDDING_ENDPOINT  = URL for http backend   (e.g. http://localhost:11434/api/embeddings)

For llama_cpp backend (default):
  Discovers binary and model by scanning from the file's own location upward.
  Works in ANY project layout as long as there's an engine/bin/llama-embedding
  somewhere near the shared/ directory.

Usage:
    from shared.embedding import get_embedding, get_embeddings
    vector = get_embedding("hello world")

    # Explicit backend selection
    from shared.embedding import EmbeddingBackend, LlamaCppBackend
    backend = LlamaCppBackend()
    vector = backend.embed("hello world")
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "llama_cpp")
EMBEDDING_ENDPOINT = os.getenv("EMBEDDING_ENDPOINT")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")  # optional override


# ── Backend ABC ────────────────────────────────────────────────────

class EmbeddingBackend(ABC):
    """Abstract embedding backend."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for *text*."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend can run in the current environment."""
        ...

    @property
    def dim(self) -> int:
        """Return the embedding dimensionality."""
        return EMBEDDING_DIM


# ── llama.cpp binary backend ──────────────────────────────────────

def _discover_llama_binary() -> Optional[Path]:
    """Find llama-embedding binary by scanning upward from this file.

    Works in ANY project layout — not tied to a specific directory structure.
    Searches:
      1. <this_file_parent>/engine/bin/llama-embedding
      2. Any parent directory + engine/bin/llama-embedding
      3. $LLAMA_EMBEDDING_BIN (explicit env override)
      4. llama-embedding in $PATH
    """
    # Explicit override
    env_bin = os.getenv("LLAMA_EMBEDDING_BIN")
    if env_bin and Path(env_bin).exists():
        return Path(env_bin)

    # Scan upward from shared/
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        candidate = parent / "engine" / "bin" / "llama-embedding"
        if candidate.exists():
            return candidate
        # Also check <parent>/bin/llama-embedding (installed layout)
        candidate = parent / "bin" / "llama-embedding"
        if candidate.exists():
            return candidate

    # PATH fallback
    import shutil
    found = shutil.which("llama-embedding")
    if found:
        return Path(found)

    return None


def _discover_llama_libs(bin_path: Path) -> Optional[Path]:
    """Find the library directory for the dynamic linker.

    Searches near the binary: ../lib, sibling lib/, or same dir.
    """
    bin_dir = bin_path.parent
    candidates = [
        bin_dir.parent / "lib",       # engine/bin/../lib
        bin_dir / "lib",              # engine/bin/lib
        bin_dir,                      # same dir as binary
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.dylib" if sys.platform == "darwin" else "*.so")):
            return c
    return None


def _discover_model() -> Optional[Path]:
    """Find an embedding model by scanning near the shared/ directory.

    Searches:
      1. EMBEDDING_MODEL env var (explicit path)
      2. models/*.gguf near this file (any parent)
      3. ~/.cache/lm-studio/models/*.gguf (LM Studio default)
    """
    # Explicit path
    if EMBEDDING_MODEL:
        p = Path(EMBEDDING_MODEL)
        if p.exists():
            return p
        # Might be a name, search in common locations
        for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
            candidate = parent / "models" / EMBEDDING_MODEL
            if candidate.exists():
                return candidate

    # Scan for any .gguf near this file
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        models_dir = parent / "models"
        if models_dir.exists():
            # Prefer f16 (smallest that's still accurate)
            for pattern in ["*_f16.gguf", "*_q8*.gguf", "*_f32.gguf", "*.gguf"]:
                matches = list(models_dir.glob(pattern))
                if matches:
                    return matches[0]

    # LM Studio default cache
    lm_models = Path.home() / ".cache" / "lm-studio" / "models"
    if lm_models.exists():
        matches = list(lm_models.glob("**/*.gguf"))
        if matches:
            return matches[0]

    return None


class LlamaCppBackend(EmbeddingBackend):
    """Embedding via bundled llama.cpp binary.

    Self-contained: no network, no external deps.
    Requires: llama-embedding binary + .gguf model file.
    """

    def __init__(self):
        self._bin = _discover_llama_binary()
        self._model = _discover_model()
        self._lib_dir = None
        if self._bin:
            self._lib_dir = _discover_llama_libs(self._bin)

    @property
    def bin_path(self) -> Optional[Path]:
        return self._bin

    @property
    def model_path(self) -> Optional[Path]:
        return self._model

    def is_available(self) -> bool:
        return self._bin is not None and self._model is not None and self._model.exists()

    def embed(self, text: str) -> list[float]:
        if not self.is_available():
            missing = []
            if not self._bin:
                missing.append("llama-embedding binary")
            if not self._model or not self._model.exists():
                missing.append("model file (.gguf)")
            raise RuntimeError(
                f"LlamaCppBackend unavailable. Missing: {', '.join(missing)}.\n"
                f"  Set LLAMA_EMBEDDING_BIN and EMBEDDING_MODEL env vars, "
                f"or place engine/bin/llama-embedding and models/*.gguf "
                f"anywhere above shared/ in the directory tree."
            )

        env = os.environ.copy()
        if self._lib_dir:
            env["DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"] = str(self._lib_dir)

        result = subprocess.run(
            [str(self._bin), "-m", str(self._model), "-p", text],
            capture_output=True, text=True, timeout=30, env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"llama-embedding failed (exit {result.returncode}):\n"
                f"  stderr: {result.stderr[:500]}\n"
                f"  stdout: {result.stdout[:200]}"
            )

        return _parse_embedding_output(result.stdout)


# ── HTTP backend (OpenAI-compatible) ──────────────────────────────

class HttpBackend(EmbeddingBackend):
    """Embedding via HTTP endpoint (OpenAI API, Ollama, etc.).

    Requires EMBEDDING_ENDPOINT env var.
    Supports OpenAI-compatible JSON API:
      POST /embeddings {"model": "...", "input": "..."}
      → {"data": [{"embedding": [...]}]}
    """

    def __init__(self):
        self._endpoint = EMBEDDING_ENDPOINT
        self._model = EMBEDDING_MODEL or "all-MiniLM-L6-v2"
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        if not self._endpoint:
            self._available = False
            return False
        try:
            import urllib.request
            import json
            # Simple connectivity check
            req = urllib.request.Request(self._endpoint, method="HEAD")
            urllib.request.urlopen(req, timeout=3)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def embed(self, text: str) -> list[float]:
        if not self._endpoint:
            raise RuntimeError(
                f"HttpBackend: no EMBEDDING_ENDPOINT configured.\n"
                f"  Set it to an OpenAI-compatible endpoint, e.g. "
                f"http://localhost:11434/api/embeddings"
            )

        import urllib.request
        import json

        body = json.dumps({"model": self._model, "input": text}).encode()
        req = urllib.request.Request(self._endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                # OpenAI format
                return data["data"][0]["embedding"]
        except Exception as e:
            raise RuntimeError(f"HttpBackend request failed: {e}") from e


# ── NoOp backend (testing / fallback) ─────────────────────────────

class NoOpBackend(EmbeddingBackend):
    """Returns zero-vectors. Useful for testing / CI / fallback."""

    def is_available(self) -> bool:
        return True

    def embed(self, text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIM


# ── Registry & default ────────────────────────────────────────────

_BACKENDS = {
    "llama_cpp": LlamaCppBackend,
    "http": HttpBackend,
    "noop": NoOpBackend,
}


def get_backend(name: Optional[str] = None) -> EmbeddingBackend:
    """Get an embedding backend by name, or the configured default."""
    backend_name = name or EMBEDDING_BACKEND
    cls = _BACKENDS.get(backend_name)
    if cls is None:
        raise ValueError(
            f"Unknown embedding backend: {backend_name!r}. "
            f"Available: {list(_BACKENDS.keys())}"
        )
    return cls()


# Module-level singleton (lazy)
_default_backend: Optional[EmbeddingBackend] = None


def _get_default_backend() -> EmbeddingBackend:
    global _default_backend
    if _default_backend is None:
        _default_backend = get_backend()
    return _default_backend


# ── Public API (unchanged for backwards compatibility) ─────────────

def get_embedding(text: str) -> list[float]:
    """Get embedding vector using the configured backend."""
    return _get_default_backend().embed(text)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for multiple texts."""
    if not texts:
        return []
    backend = _get_default_backend()
    return [backend.embed(t) for t in texts]


# ── Legacy helpers (for backwards compatibility with existing servers) ──

def _ensure_binaries() -> bool:
    """Check if the llama.cpp binary and model are available.

    Legacy alias — works for any backend.
    """
    return _get_default_backend().is_available()


def _get_llama_cmd() -> Optional[str]:
    """Return path to llama-embedding binary, or None.

    Only meaningful for LlamaCppBackend. Returns None for other backends.
    """
    backend = _get_default_backend()
    if isinstance(backend, LlamaCppBackend):
        return str(backend.bin_path) if backend.bin_path else None
    return None


# ── Internal helpers ──────────────────────────────────────────────

def _parse_embedding_output(stdout: str) -> list[float]:
    """Parse llama-embedding text output.

    Format: "embedding 0: -0.034495  0.030879  ..."
    """
    for line in stdout.split('\n'):
        if line.startswith('embedding '):
            match = re.search(r':\s*(.+)', line)
            if match:
                nums = match.group(1).strip().split()
                result = []
                for x in nums:
                    try:
                        result.append(float(x))
                    except ValueError:
                        continue
                if result:
                    return result
    raise ValueError(f"No embedding found in output: {stdout[:200]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Get embeddings via configured backend")
    parser.add_argument("text", nargs="+", help="Text(s) to embed")
    parser.add_argument("--backend", choices=list(_BACKENDS.keys()), default=None)
    args = parser.parse_args()

    backend = get_backend(args.backend)
    print(f"Backend: {backend.__class__.__name__}")
    print(f"Available: {backend.is_available()}")
    print(f"Dim: {backend.dim}")

    if len(args.text) == 1:
        vec = backend.embed(args.text[0])
        print(f"Embedding: {len(vec)} dimensions")
        print(f"First 5: {[round(v, 6) for v in vec[:5]]}")
    else:
        vecs = [backend.embed(t) for t in args.text]
        print(f"Generated {len(vecs)} embeddings, each {len(vecs[0])} dimensions")
