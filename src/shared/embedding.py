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
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))  # BGE-M3 default
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "llama_cpp")
EMBEDDING_ENDPOINT = os.getenv("EMBEDDING_ENDPOINT")
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL", "bge-m3") # Default model ID
EMBEDDING_VERSION = os.getenv("EMBEDDING_VERSION", "v1")
EMBEDDING_METRIC = os.getenv("EMBEDDING_METRIC", "cosine")
EMBEDDING_STRICT = os.getenv("EMBEDDING_STRICT", "true").lower() == "true"


@dataclass(frozen=True)
class EmbeddingSpec:
    """Explicit contract for embeddings."""
    backend: str
    model_id: str
    dim: int
    metric: str
    version: str

    @property
    def key(self) -> str:
        """Stable key for this embedding configuration."""
        return f"{self.backend}:{self.model_id}:{self.dim}:{self.metric}:{self.version}"


def get_embedding_spec() -> EmbeddingSpec:
    """Get the current embedding specification."""
    return EmbeddingSpec(
        backend=EMBEDDING_BACKEND,
        model_id=EMBEDDING_MODEL_ID,
        dim=EMBEDDING_DIM,
        metric=EMBEDDING_METRIC,
        version=EMBEDDING_VERSION,
    )


def _validate_embedding_vector(vector: list[float], spec: EmbeddingSpec) -> list[float]:
    """Ensure the vector matches the expected dimensionality."""
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Embedding backend returned empty or invalid vector")
    
    if len(vector) != spec.dim:
        raise RuntimeError(
            f"Embedding dimension mismatch: expected {spec.dim}, got {len(vector)} "
            f"from model={spec.model_id} backend={spec.backend} version={spec.version}"
        )
    return vector


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
      1. EMBEDDING_MODEL_ID env var (explicit path or name)
      2. Specific model patterns near this file (any parent)
      3. LM Studio default cache
    """
    # Explicit path
    if EMBEDDING_MODEL_ID:
        p = Path(EMBEDDING_MODEL_ID)
        if p.exists():
            return p
        # Might be a name, search in common locations
        for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
            candidate = parent / "models" / EMBEDDING_MODEL_ID
            if candidate.exists():
                return candidate

    # Scan for model patterns near this file
    current = Path(__file__).resolve()
    
    # In production, we ONLY want specific models.
    # If EMBEDDING_STRICT is true, we don't allow generic fallbacks.
    strict_patterns = ["*bge*m3*.gguf", "*bge*.gguf"] if EMBEDDING_STRICT else [
        "*bge*m3*.gguf",        # BGE-M3 (1024 dims, best)
        "*bge*.gguf",            # Any BGE
        "*nomic*embed*.gguf",    # Nomic (768 dims)
        "*_f16.gguf",            # MiniLM f16 (384 dims)
        "*_q8*.gguf",            # MiniLM q8
        "*_f32.gguf",            # MiniLM f32
        "*.gguf",                # Any gguf (only if not strict)
    ]

    for parent in [current] + list(current.parents):
        models_dir = parent / "models"
        if models_dir.exists():
            for pattern in strict_patterns:
                matches = list(models_dir.glob(pattern))
                if matches:
                    return matches[0]

    if EMBEDDING_STRICT:
        # In strict mode, if we haven't found a BGE model, we FAIL.
        # Don't even try LM Studio fallback.
        return None

    # LM Studio default cache (fallback only if not strict)
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

        vector = _parse_embedding_output(result.stdout)
        return _validate_embedding_vector(vector, get_embedding_spec())


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
        token_hash = int(hashlib.md5(token.encode()).hexdigest()[:8], 16)
        indices.append(token_hash)
        values.append(float(count))

    return {"indices": indices, "values": values}


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
                vector = data["data"][0]["embedding"]
                return _validate_embedding_vector(vector, get_embedding_spec())
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
    Requires llama-server running as a daemon process.

    Env vars:
      LLAMA_SERVER_URL  — Server URL (default: http://127.0.0.1:8080)
    """

    def __init__(self):
        self._url = os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8080")
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

        body = _json.dumps({"content": text}).encode()
        req = urllib.request.Request(
            f"{self._url}/embedding",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
            # llama-server format: [{"index": 0, "embedding": [[float, ...]]}]
            # or: {"embedding": [float, ...]}
            vector = []
            if isinstance(data, list) and data:
                emb = data[0].get("embedding", [])
                # Some versions wrap in an extra list
                if isinstance(emb, list) and emb and isinstance(emb[0], list):
                    vector = emb[0]
                else:
                    vector = emb
            elif isinstance(data, dict):
                emb = data.get("embedding", [])
                if isinstance(emb, list) and emb and isinstance(emb[0], list):
                    vector = emb[0]
                else:
                    vector = emb
            else:
                raise ValueError(f"Unexpected embedding response format: {type(data)}")
            
            return _validate_embedding_vector(vector, get_embedding_spec())


# ── LRU Cache ──────────────────────────────────────────────────────

class EmbeddingCache:
    """Simple LRU cache for embeddings. Same text = same vector, no call."""

    def __init__(self, backend: EmbeddingBackend, maxsize: int = 512):
        self._backend = backend
        self._maxsize = maxsize
        self._cache: dict[str, list[float]] = {}
        self._order: list[str] = []  # LRU order (oldest first)
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache), "maxsize": self._maxsize}

    def embed(self, text: str) -> list[float]:
        # Use hash for long texts to save memory
        key = text if len(text) <= 200 else f"__hash:{hash(text)}"

        if key in self._cache:
            # Move to end (most recently used)
            self._order.remove(key)
            self._order.append(key)
            self._hits += 1
            return self._cache[key]

        # Cache miss — compute
        vector = self._backend.embed(text)

        self._cache[key] = vector
        self._order.append(key)
        self._misses += 1

        # Evict oldest if over capacity
        while len(self._cache) > self._maxsize:
            oldest = self._order.pop(0)
            self._cache.pop(oldest, None)

        return vector

    def is_available(self) -> bool:
        return self._backend.is_available()

    @property
    def dim(self) -> int:
        return self._backend.dim


# ── Circuit Breaker ───────────────────────────────────────────────

class CircuitBreaker:
    """Circuit breaker for embedding backends.

    States:
      CLOSED   — Normal operation. Requests go through.
      OPEN     — Too many failures. Requests fail fast / fallback.
      HALF_OPEN — Testing recovery. One request allowed.

    Configuration:
      FAILURE_THRESHOLD  — Consecutive failures before opening (default: 3)
      RECOVERY_TIMEOUT   — Seconds before trying half-open (default: 30)
      HALF_OPEN_MAX      — Consecutive successes in half-open to close (default: 2)
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str = "embedding",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            # Auto-transition from OPEN → HALF_OPEN after timeout
            if self._state == self.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._success_count = 0
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    def record_success(self) -> str:
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max:
                    self._state = self.CLOSED
                    self._failure_count = 0
            elif self._state == self.CLOSED:
                self._failure_count = 0
            return self._state

    def record_failure(self) -> str:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
            elif self._state == self.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = self.OPEN
            return self._state

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# Module-level circuit breaker for llama-server
_llama_server_breaker = CircuitBreaker(
    name="llama-server",
    failure_threshold=int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3")),
    recovery_timeout=float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "30")),
    half_open_max=int(os.getenv("CIRCUIT_BREAKER_HALF_OPEN_MAX", "2")),
)


def _embed_with_retry(
    backend: EmbeddingBackend,
    text: str,
    max_retries: int = 2,
    initial_delay: float = 0.5,
    breaker: CircuitBreaker | None = None,
    fallback_backend: EmbeddingBackend | None = None,
) -> list[float]:
    """Embed with retry + circuit breaker + fallback.

    Strategy:
      1. If circuit breaker is OPEN → use fallback immediately
      2. Try primary backend with exponential backoff
      3. On success → record_success on breaker
      4. On all retries exhausted → record_failure on breaker, try fallback
    """
    # Fast path: circuit open → fallback
    if breaker and breaker.is_open:
        if fallback_backend and fallback_backend.is_available():
            return fallback_backend.embed(text)
        # No fallback available, try anyway (breaker might be stale)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = backend.embed(text)
            if breaker:
                breaker.record_success()
            return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = initial_delay * (2 ** attempt)  # exponential backoff
                time.sleep(delay)

    # All retries exhausted
    if breaker:
        breaker.record_failure()

    # Try fallback
    if fallback_backend and fallback_backend.is_available():
        try:
            return fallback_backend.embed(text)
        except Exception:
            pass  # Fallback also failed, raise original error

    raise last_error  # type: ignore


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


# Module-level singleton (lazy)
_default_backend: Optional[EmbeddingBackend] = None


def _get_default_backend() -> EmbeddingBackend:
    """Get the default backend, with auto-detection and caching.

    Priority: llama_server (if running) > configured backend.
    Always wrapped in LRU cache.
    """
    global _default_backend
    if _default_backend is not None:
        return _default_backend

    # If user explicitly requested a backend, respect that
    explicit = os.getenv("EMBEDDING_BACKEND")
    if explicit:
        backend = get_backend(explicit)
    else:
        # Auto-detect: try server first, fallback to subprocess
        server = LlamaServerBackend()
        if server.is_available():
            backend = server
        else:
            backend = LlamaCppBackend()

    # Wrap in LRU cache
    _default_backend = EmbeddingCache(backend, maxsize=int(os.getenv("EMBEDDING_CACHE_SIZE", "512")))
    return _default_backend


# ── Public API (unchanged for backwards compatibility) ─────────────

def get_embedding(text: str) -> list[float]:
    """Get embedding vector using the configured backend (cached).

    For LlamaServerBackend: uses circuit breaker + retry + fallback to subprocess.
    For other backends: direct call through LRU cache.
    """
    backend = _get_default_backend()
    # Unwrap cache to check inner backend
    inner = backend._backend if isinstance(backend, EmbeddingCache) else backend

    if isinstance(inner, LlamaServerBackend):
        # Circuit breaker + retry + fallback to subprocess
        fallback = LlamaCppBackend()
        vector = _embed_with_retry(
            backend=inner,
            text=text,
            max_retries=2,
            initial_delay=0.3,
            breaker=_llama_server_breaker,
            fallback_backend=fallback if fallback.is_available() else None,
        )
        # Update cache
        if isinstance(backend, EmbeddingCache):
            key = text if len(text) <= 200 else f"__hash:{hash(text)}"
            backend._cache[key] = vector
        return vector

    return backend.embed(text)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for multiple texts."""
    if not texts:
        return []
    backend = _get_default_backend()
    return [backend.embed(t) for t in texts]


def get_cache_stats() -> dict:
    """Get embedding cache statistics + circuit breaker state."""
    backend = _get_default_backend()
    stats: dict = {"hits": 0, "misses": 0, "size": 0, "maxsize": 0}
    if isinstance(backend, EmbeddingCache):
        stats = backend.stats
    stats["circuit_breaker"] = _llama_server_breaker.stats
    return stats


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
