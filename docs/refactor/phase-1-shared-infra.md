# Phase 1: Shared Infrastructure

**Duration**: 2-3 days
**Goal**: Eliminate code duplication by creating centralized shared modules

---

## Spec

### 1.1 New: `shared/qdrant_client.py`

Centralized Qdrant HTTP operations. All servers import this instead of raw httpx.

```python
class QdrantClient:
    def __init__(self, url: str, collection: str, embedding_dim: int = 1024)
    async def health(self) -> bool
    async def ensure_collection(self, sparse: bool = True)
    async def upsert(self, point_id: str, vector: list[float], payload: dict, sparse: dict = None)
    async def search(self, vector: list[float], limit: int, threshold: float, filter: dict = None) -> list[dict]
    async def scroll(self, filter: dict, limit: int) -> list[dict]
    async def get(self, point_id: str) -> dict | None
    async def count(self) -> int
```

### 1.2 New: `shared/config.py`

Centralized configuration with type-safe access and validation.

```python
class Config:
    qdrant_url: str
    qdrant_collection: str
    embedding_dim: int
    embedding_backend: str
    llama_server_url: str
    vault_path: Path
    engram_path: Path
    dream_path: Path

    @classmethod
    def from_env(cls) -> Config
    def validate(self) -> list[str]  # returns errors
```

### 1.3 Refactor: `shared/embedding.py`

- Replace custom `EmbeddingCache` with `@functools.lru_cache(maxsize=512)`
- Fix global `_default_backend` state: use `threading.Lock` or factory pattern
- Add `async_embed_batch(texts: list[str])` for batch operations
- Keep backward-compatible `get_embedding()`, `async_embed()`, `bm25_tokenize()`

### 1.4 Refactor: `shared/env_loader.py`

- Remove auto-load at module level (`_loaded_from = load_env()`)
- Keep `load_env()` as callable function
- Add `get_config() -> Config` that calls `load_env()` then returns Config

## Checklist

- [ ] Create `shared/qdrant_client.py` with QdrantClient class
- [ ] Create `shared/config.py` with Config class
- [ ] Refactor `shared/embedding.py` (lru_cache, fix global state)
- [ ] Refactor `shared/env_loader.py` (remove auto-load)
- [ ] Unit test: qdrant_client.py (mock httpx)
- [ ] Unit test: config.py (env parsing)
- [ ] Verify: existing server modules still work with refactored shared/

## Acceptance Criteria

- [ ] Zero raw `httpx` Qdrant calls outside `shared/qdrant_client.py`
- [ ] Zero `os.getenv()` outside `shared/config.py` (except in config.py and env_loader.py)
- [ ] `shared/embedding.py` uses `functools.lru_cache` (no custom LRU)
- [ ] `shared/env_loader.py` does NOT auto-load on import
- [ ] All existing tests pass
