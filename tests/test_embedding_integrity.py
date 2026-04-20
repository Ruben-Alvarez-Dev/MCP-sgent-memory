"""Production embedding integrity — real metrics, zero shortcuts.

Every test here calls the actual functions and measures real outputs.
No source-scanning, no keyword-regex. Prove it works or fail.
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── Embedding pipeline produces real, correctly-sized vectors ──────


class TestEmbeddingPipeline:
    """Verify every embedding consumer returns vectors matching the spec."""

    def test_shared_embedding_dim_is_1024(self):
        """The canonical EMBEDDING_DIM must be 1024."""
        from shared.embedding import EMBEDDING_DIM
        assert EMBEDDING_DIM == 1024

    def test_noop_backend_vector_matches_dim(self):
        """NoOpBackend.embed() must return a vector of length EMBEDDING_DIM."""
        from shared.embedding import NoOpBackend, EMBEDDING_DIM
        vec = NoOpBackend().embed("test input")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vec)

    def test_validation_catches_wrong_dim(self):
        """_validate_embedding_vector must raise on a 384-dim vector when spec says 1024."""
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        spec = get_embedding_spec()
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            _validate_embedding_vector([0.1] * 384, spec)

    def test_validation_passes_on_correct_dim(self):
        """_validate_embedding_vector must accept a vector that matches the spec."""
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        spec = get_embedding_spec()
        vec = [0.1] * spec.dim
        result = _validate_embedding_vector(vec, spec)
        assert result is vec

    def test_validation_rejects_empty(self):
        """_validate_embedding_vector must reject empty lists."""
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        with pytest.raises(RuntimeError, match="empty or invalid"):
            _validate_embedding_vector([], get_embedding_spec())


# ── EmbeddingSpec is a real frozen contract ────────────────────────


class TestEmbeddingSpecContract:
    """EmbeddingSpec must be immutable, complete, and produce a stable key."""

    def test_spec_is_frozen(self):
        from shared.embedding import EmbeddingSpec
        spec = EmbeddingSpec(backend="llama_cpp", model_id="bge-m3", dim=1024, metric="cosine", version="v1")
        with pytest.raises(AttributeError):
            spec.dim = 384  # type: ignore[misc]

    def test_spec_key_has_all_fields(self):
        from shared.embedding import get_embedding_spec
        key = get_embedding_spec().key
        parts = key.split(":")
        assert len(parts) == 5, f"key must have 5 colon-separated parts, got: {key}"
        assert parts[2].isdigit(), f"dim part must be numeric, got: {parts[2]}"

    def test_default_spec_values(self):
        from shared.embedding import get_embedding_spec
        spec = get_embedding_spec()
        assert spec.dim == 1024
        assert spec.metric == "cosine"
        assert spec.version == "v1"
        assert spec.model_id == "bge-m3"


# ── Retrieval module delegates to real embedding ───────────────────


class TestRetrievalDelegation:
    """retrieval.get_embedding must call the real shared.embedding backend."""

    def test_retrieval_get_embedding_is_wired(self):
        """retrieval.get_embedding must delegate to shared.embedding.get_embedding."""
        import shared.retrieval as retrieval_mod
        import shared.embedding as embedding_mod
        assert retrieval_mod._real_get_embedding is embedding_mod.get_embedding

    def test_retrieval_classify_intent_returns_real_structure(self):
        """classify_intent must return a QueryIntent with real classified fields."""
        from shared.retrieval import classify_intent
        from shared.llm.config import QueryIntent

        # Code lookup
        intent = classify_intent("where is the EmbeddingBackend class defined?")
        assert isinstance(intent, QueryIntent)
        assert intent.intent_type == "code_lookup"
        assert intent.scope == "this_project"

        # Debug
        intent = classify_intent("error: cannot import debug_traceback")
        assert intent.intent_type == "debug"

        # Plan
        intent = classify_intent("how should we architect the auth module?")
        assert intent.intent_type == "plan"
        assert intent.needs_ranking is True

        # External scope
        intent = classify_intent("what does the latest docs say about the library?")
        assert intent.scope == "external"
        assert intent.needs_external is True

    def test_retrieval_prune_content_real_truncation(self):
        """prune_content must actually truncate, not return hardcoded strings."""
        from shared.retrieval import prune_content

        source = "def alpha():\n    x = 1\n    return x\n\ndef beta():\n    return 'ok'\n"
        result = prune_content(source, path="test.py", max_tokens=3)
        # max_tokens=3 → ~12 chars, must be shorter than original
        assert len(result) < len(source)
        assert "def" in result  # Should preserve the function signature

    def test_retrieval_prune_content_passthrough_when_fits(self):
        """prune_content must return original content when it fits within budget."""
        from shared.retrieval import prune_content
        short = "hello"
        assert prune_content(short, max_tokens=100) == short


# ── Qdrant payloads carry embedding_spec ───────────────────────────


class TestQdrantPayloadIntegrity:
    """Every point upserted to Qdrant must carry its embedding_spec for traceability."""

    @pytest.mark.asyncio
    async def test_payload_includes_embedding_spec(self, tmp_path: Path):
        from shared.retrieval.index_repo import _build_code_map_points
        from shared.embedding import get_embedding_spec

        (tmp_path / "example.py").write_text("def hello():\n    return 'world'\n")

        spec = get_embedding_spec()

        async def embed_fn(text: str) -> list[float]:
            return [0.1] * spec.dim

        points = await _build_code_map_points(str(tmp_path), embed_fn)
        assert len(points) >= 1

        for point in points:
            es = point["payload"].get("embedding_spec")
            assert es is not None, f"Point missing embedding_spec: {point['id']}"
            assert es["dim"] == spec.dim
            assert es["model_id"] == spec.model_id
            assert es["version"] == spec.version
            assert es["backend"] == spec.backend
            assert "key" in es

    @pytest.mark.asyncio
    async def test_vector_dimension_matches_spec(self, tmp_path: Path):
        """The vector in each point must match EMBEDDING_DIM from the spec."""
        from shared.retrieval.index_repo import _build_code_map_points
        from shared.embedding import get_embedding_spec

        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")

        spec = get_embedding_spec()

        async def embed_fn(text: str) -> list[float]:
            return [0.5] * spec.dim

        points = await _build_code_map_points(str(tmp_path), embed_fn)

        for point in points:
            assert len(point["vector"]) == spec.dim, (
                f"Vector has {len(point['vector'])} dims, expected {spec.dim}"
            )


# ── vk-cache wired to real async_embed ─────────────────────────────


class TestVkCacheWiring:
    """vk-cache/server must use async_embed from shared.embedding."""

    def test_imports_async_embed(self):
        import importlib
        vk_main = importlib.import_module("vk-cache.server.main")
        assert hasattr(vk_main, "async_embed"), "vk-cache must import async_embed"

    def test_no_legacy_llama_embed_func(self):
        import importlib
        vk_main = importlib.import_module("vk-cache.server.main")
        assert not hasattr(vk_main, "_llama_embed_func"), (
            "Old _llama_embed_func placeholder must be removed"
        )

    def test_async_embed_is_from_shared(self):
        import importlib
        import shared.embedding as emb
        vk_main = importlib.import_module("vk-cache.server.main")
        assert vk_main.async_embed is emb.async_embed


# ── _rank_and_fuse requires real LLM function ──────────────────────


class TestRankAndFuseContract:
    """_rank_and_fuse must not invent fake LLM responses."""

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_without_llm_fn(self):
        """When needs_ranking=True but no llm_fn provided, sort by score, don't crash."""
        from shared.retrieval import _rank_and_fuse
        from shared.llm.config import ContextItem, QueryIntent

        items = {
            "L1": [
                ContextItem(content="low", score=0.3, source_name="L1", source_level=1),
                ContextItem(content="high", score=0.9, source_name="L1", source_level=1),
            ]
        }
        intent = QueryIntent(
            intent_type="debug", entities=[], scope="this_project",
            time_window="all", needs_external=False, needs_ranking=True,
            needs_consolidation=False,
        )
        result = await _rank_and_fuse(items, intent, "query")
        # Must not crash, must return items sorted by score
        assert len(result) == 2
        assert result[0].score >= result[1].score

    @pytest.mark.asyncio
    async def test_uses_real_llm_fn_when_provided(self):
        from shared.retrieval import _rank_and_fuse
        from shared.llm.config import ContextItem, QueryIntent

        items = {
            "L1": [
                ContextItem(content="A", score=0.1, source_name="L1", source_level=1),
                ContextItem(content="B", score=0.9, source_name="L1", source_level=1),
            ]
        }
        intent = QueryIntent(
            intent_type="debug", entities=[], scope="this_project",
            time_window="all", needs_external=False, needs_ranking=True,
            needs_consolidation=False,
        )

        async def real_llm(prompt: str) -> str:
            return '{"ranked_indices": [1, 0]}'

        result = await _rank_and_fuse(items, intent, "query", llm_fn=real_llm)
        assert result[0].content == "A"  # Reordered by LLM
        assert result[1].content == "B"
