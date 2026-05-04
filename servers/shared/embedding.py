"""Embedding abstraction — agnostic backend system.

Provides a unified interface for generating embeddings with swappable backends:
  - llama_cpp: Bundled llama.cpp binary (default, self-contained)
  - http:       Any HTTP endpoint that returns embeddings (OpenAI, etc.)
  - noop:       Returns zero-vectors (testing / fallback)

Configuration is entirely env-driven and project-agnostic:
  EMBEDDING_BACKEND   = llama_cpp | http | noop  (default: llama_cpp)
  EMBEDDING_MODEL     = model path or name (backend-specific)
  EMBEDDING_DIM       = vector dimensionality  (default: 384)
  EMBEDDING_ENDPOINT  = URL for http backend   (e.g. http://localhost:8081/v1/embeddings)

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

import logging
import os

logger = logging.getLogger(__name__)
import re
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))  # BGE-M3 default
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
            # Preference: BGE-M3 > Nomic > MiniLM
            for pattern in [
                "*bge*m3*.gguf",        # BGE-M3 (1024 dims, best)
                "*bge*.gguf",            # Any BGE
                "*nomic*embed*.gguf",    # Nomic (768 dims)
                "*_f16.gguf",            # MiniLM f16 (384 dims)
                "*_q8*.gguf",            # MiniLM q8
                "*_f32.gguf",            # MiniLM f32
                "*.gguf",                # Any gguf
            ]:
                matches = list(models_dir.glob(pattern))
                if matches:
                    return matches[0]

    # LM Studio default cache (fallback only)
    lm_models = Path(os.getenv("LM_STUDIO_MODELS", str(Path.home() / ".cache" / "lm-studio" / "models")))
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

        # Sanitize text: llama-embedding splits on newlines creating multiple embeddings
        clean_text = text.replace("\n", " ").replace("\r", " ")
        # Truncate to avoid excessive tokenization (1024 tokens ≈ 4096 chars)
        clean_text = clean_text[:2000]

        result = subprocess.run(
            [str(self._bin), "-m", str(self._model), "-p", clean_text, "--pooling", "mean"],
            capture_output=True, text=True, timeout=30, env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"llama-embedding failed (exit {result.returncode}):\n"
                f"  stderr: {result.stderr[:500]}\n"
                f"  stdout: {result.stdout[:200]}"
            )

        return _parse_embedding_output(result.stdout)


# ── BM25 Sparse Vector Tokenizer ─────────────────────────────────

# Common stop words for BM25 sparse vectors
_STOP_WORDS = frozenset([
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "it", "its", "this", "that", "these", "those",
    "i", "you", "he", "she", "we", "they", "what", "which", "who",
    "whom", "whose", "where", "when", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "because", "as", "until", "while", "about",
    "between", "through", "during", "before", "after", "above",
    "below", "up", "down", "out", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "into", "also",
    "el", "la", "los", "las", "un", "una", "de", "del", "que",
    "y", "o", "pero", "con", "sin", "para", "por", "se", "su",
    "como", "muy", "es", "son", "tiene", "tener",
])


def bm25_tokenize(text: str) -> dict:
    """Tokenize text for BM25 sparse vector (Qdrant format).

    Returns {"indices": [...], "values": [...]} for Qdrant sparse vector upsert.
    Qdrant computes IDF server-side; we just send term frequencies.
    """
    import hashlib

    text = text.lower()
    # Split on non-alphanumeric, keep alphanumeric + underscores
    tokens = re.findall(r'[a-z0-9_]{2,}', text)
    # Filter stop words
    tokens = [t for t in tokens if t not in _STOP_WORDS]
    if not tokens:
        return {"indices": [], "values": []}

    # Count frequencies
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1

    # Convert to Qdrant format: indices are hashes, values are frequencies
    indices = []
    values = []
    for token, count in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        # Use 32-bit hash for token ID
        token_hash = hash(token) & 0xFFFFFFFF
        indices.append(token_hash)
        values.append(float(count))

    return {"indices": indices, "values": values}


# ── HTTP backend (OpenAI-compatible) ──────────────────────────────

class HttpBackend(EmbeddingBackend):
    """Embedding via HTTP endpoint (OpenAI API, etc.).

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
                f"http://localhost:8081/v1/embeddings"
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


# ── llama-server HTTP backend (72x faster than subprocess) ─────────

class LlamaServerBackend(EmbeddingBackend):
    """Embedding via persistent llama-server HTTP daemon.

    ~15ms per call vs ~1,087ms for subprocess (72x faster).
    Supports batch embeddings via /v1/embeddings OpenAI API (1.6x faster).
    Requires llama-server running as a daemon process.

    Env vars:
      LLAMA_SERVER_URL  — Server URL (default: http://127.0.0.1:8080)
     """

    def __init__(self):
        self._url = os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8081")
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._url}/health", method="GET")
            urllib.request.urlopen(req, timeout=2)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def embed(self, text: str) -> list[float]:
        import urllib.request
        import json as _json

        body = _json.dumps({"input": text, "model": "BGE-M3"}).encode()
        req = urllib.request.Request(
            f"{self._url}/v1/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
            if isinstance(data, dict) and "data" in data:
                items = data["data"]
                if items and isinstance(items, list):
                    return items[0].get("embedding", [])
            raise ValueError(f"Unexpected embedding response format: {type(data)}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed via /v1/embeddings OpenAI-compatible API.

        1.6x faster than individual calls for 10+ texts.
        """
        import urllib.request
        import json as _json

        body = _json.dumps({"input": texts, "model": "bge-m3"}).encode()
        req = urllib.request.Request(
            f"{self._url}/v1/embeddings",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
            if "data" in data:
                results = sorted(data["data"], key=lambda x: x.get("index", 0))
                return [r["embedding"] for r in results]
            raise ValueError(f"Unexpected batch response: {str(data)[:200]}")


# ── LRU Cache ──────────────────────────────────────────────────────

_cache_hits = 0
_cache_misses = 0


def _get_cache_stats() -> dict[str, int]:
    return {"hits": _cache_hits, "misses": _cache_misses}


# ── Registry & default ────────────────────────────────────────────

_BACKENDS = {
    "llama_cpp": LlamaCppBackend,
    "llama_server": LlamaServerBackend,
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


# Module-level singleton (thread-safe)
_default_backend: Optional[EmbeddingBackend] = None
_backend_lock = threading.Lock()
_backend_cache_fn = None


def _get_default_backend() -> EmbeddingBackend:
    """Get the default backend with thread-safe initialization."""
    global _default_backend, _backend_cache_fn
    if _default_backend is not None:
        return _default_backend

    with _backend_lock:
        if _default_backend is not None:
            return _default_backend

        explicit = os.getenv("EMBEDDING_BACKEND")
        if explicit:
            backend = get_backend(explicit)
        else:
            server = LlamaServerBackend()
            if server.is_available():
                backend = server
            else:
                backend = LlamaCppBackend()

        _default_backend = backend

        # Create lru_cache wrapper for embed calls
        maxsize = int(os.getenv("EMBEDDING_CACHE_SIZE", "512"))

        @lru_cache(maxsize=maxsize)
        def _cached_embed(text: str) -> tuple:
            global _cache_misses
            _cache_misses += 1
            return tuple(backend.embed(text))

        _backend_cache_fn = _cached_embed

    return _default_backend


# ── Public API (unchanged for backwards compatibility) ─────────────

def get_embedding(text: str) -> list[float]:
    """Get embedding vector using the configured backend (cached via lru_cache + SQLite)."""
    global _cache_hits
    _get_default_backend()  # ensure initialized

    # Smart truncate long texts to avoid slow tokenization
    if len(text) > 2000:
        from shared.text import smart_truncate
        text = smart_truncate(text, 2000)

    # 1. Check in-memory LRU cache
    cache_key = text if len(text) <= 200 else text[:200]
    if _backend_cache_fn is not None:
        result = _backend_cache_fn(cache_key)
        if result and isinstance(result, tuple):
            _cache_hits += 1
            vec = list(result)
            # Also populate persistent cache for restart survival
            from shared.embedding_cache import cache_set
            cache_set(text, vec)
            return vec

    # 2. Check persistent SQLite cache
    from shared.embedding_cache import cache_get, cache_set
    cached = cache_get(text)
    if cached and len(cached) > 0:
        _cache_hits += 1
        return cached

    # 3. Compute embedding
    vec = _default_backend.embed(text)

    # 4. Store to persistent cache
    if vec and len(vec) > 0:
        cache_set(text, vec)

    return vec


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for multiple texts."""
    if not texts:
        return []
    backend = _get_default_backend()
    return [backend.embed(t) for t in texts]


def get_cache_stats() -> dict[str, int]:
    """Get embedding cache statistics."""
    global _cache_hits, _cache_misses
    if _backend_cache_fn is not None:
        info = _backend_cache_fn.cache_info()
        return {"hits": info.hits, "misses": info.misses, "size": info.currsize, "maxsize": info.maxsize}
    return {"hits": _cache_hits, "misses": _cache_misses, "size": 0, "maxsize": 0}


# ── Legacy helpers (for backwards compatibility with existing servers) ──

def _ensure_binaries() -> bool:
    """Check if the embedding backend is available.

    Works for any backend, not just llama_cpp.
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


async def async_embed(text: str) -> list[float]:
    """Async wrapper — run embedding in thread pool.

    Use this from MCP servers instead of duplicating embed_text() everywhere.
    Handles backend initialization transparently.
    """
    import asyncio
    return await asyncio.to_thread(get_embedding, text)


async def safe_embed(text: str) -> list[float]:
    """Embed with fallback to zero-vector and warning log.

    Never returns empty list. If embedding fails, returns a zero-vector
    of the configured dimension and logs a warning.
    Use this as the safe replacement for local _embed() wrappers.
    """
    import asyncio as _aio
    try:
        vec = await async_embed(text)
        if vec and len(vec) > 0:
            return vec
    except Exception as e:
        logger.warning("safe_embed: embedding failed, using zero-vector: %s", e)
    dim = int(os.getenv("EMBEDDING_DIM", "1024"))
    logger.warning("safe_embed: returning zero-vector of dim=%d for text='%s'", dim, text[:80])
    return [0.0] * dim


async def async_embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts efficiently using batch API when available.

    Uses LlamaServerBackend.embed_batch() for 1.6x speedup on 10+ texts.
    Falls back to individual embeds with parallel thread pool.
    """
    import asyncio as _aio
    if not texts:
        return []

    # Try batch embedding if backend supports it
    backend = _get_default_backend()
    if hasattr(backend, 'embed_batch'):
        try:
            vecs = await asyncio.to_thread(backend.embed_batch, texts)
            return vecs
        except Exception as e:
            logger.warning("async_embed_batch: batch failed, falling back: %s", e)

    # Fallback: individual embeddings in parallel
    results = await asyncio.gather(
        *[safe_embed(t) for t in texts],
        return_exceptions=True,
    )
    output = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.warning("async_embed_batch: item %d failed: %s", i, r)
            dim = int(os.getenv("EMBEDDING_DIM", "1024"))
            output.append([0.0] * dim)
        else:
            output.append(r)
    return output


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
