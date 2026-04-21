"""Production embedding integrity — real metrics, zero shortcuts."""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestEmbeddingPipeline:
    def test_shared_embedding_dim_is_1024(self):
        from shared.embedding import EMBEDDING_DIM
        assert EMBEDDING_DIM == 1024

    def test_noop_backend_vector_matches_dim(self):
        from shared.embedding import NoOpBackend, EMBEDDING_DIM
        vec = NoOpBackend().embed("test input")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vec)

    def test_validation_catches_wrong_dim(self):
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        spec = get_embedding_spec()
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            _validate_embedding_vector([0.1] * 384, spec)

    def test_validation_passes_on_correct_dim(self):
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        spec = get_embedding_spec()
        vec = [0.1] * spec.dim
        result = _validate_embedding_vector(vec, spec)
        assert result is vec

    def test_validation_rejects_empty(self):
        from shared.embedding import _validate_embedding_vector, get_embedding_spec
        with pytest.raises(RuntimeError, match="empty or invalid"):
            _validate_embedding_vector([], get_embedding_spec())


class TestEmbeddingSpecContract:
    def test_spec_is_frozen(self):
        from shared.embedding import EmbeddingSpec
        spec = EmbeddingSpec(backend="llama_cpp", model_id="bge-m3", dim=1024, metric="cosine", version="v1")
        with pytest.raises(AttributeError):
            spec.dim = 384

    def test_spec_key_has_all_fields(self):
        from shared.embedding import get_embedding_spec
        key = get_embedding_spec().key
        parts = key.split(":")
        assert len(parts) == 5
        assert parts[2].isdigit()

    def test_default_spec_values(self):
        from shared.embedding import get_embedding_spec
        spec = get_embedding_spec()
        assert spec.dim == 1024
        assert spec.metric == "cosine"


class TestRetrievalDelegation:
    def test_retrieval_uses_shared_embedding(self):
        import shared.retrieval as retrieval_mod
        import shared.embedding as embedding_mod
        assert retrieval_mod.get_embedding is embedding_mod.get_embedding

    def test_retrieval_classify_intent_returns_real_structure(self):
        from shared.retrieval import classify_intent
        from shared.llm.config import QueryIntent

        intent = classify_intent("where is the EmbeddingBackend class defined?")
        assert isinstance(intent, QueryIntent)
        assert intent.intent_type == "code_lookup"
        assert intent.scope == "this_project"

        # Debug is now pattern_match in the restored classifier
        intent2 = classify_intent("error: cannot import debug_traceback")
        assert isinstance(intent2, QueryIntent)

    def test_retrieval_prune_content_real_truncation(self):
        from shared.retrieval import prune_content
        source = "def alpha():\n    x = 1\n    return x\n\ndef beta():\n    return 'ok'\n"
        result = prune_content(source, path="test.py", max_tokens=3)
        # Result should be shorter than source
        assert len(result) < len(source)

    def test_retrieval_prune_content_passthrough_when_fits(self):
        from shared.retrieval import prune_content
        short = "hello"
        assert prune_content(short, max_tokens=100) == short


class TestQdrantPayloadIntegrity:
    @pytest.mark.asyncio
    async def test_code_map_points_include_vectors(self, tmp_path: Path):
        from shared.retrieval.index_repo import build_code_map_points
        from shared.embedding import get_embedding_spec
        (tmp_path / "example.py").write_text("def hello():\n    return 'world'\n")
        spec = get_embedding_spec()
        def embed_fn(text: str) -> list[float]:
            return [0.1] * spec.dim
        # build_code_map_points takes project_root and optional embed_fn
        points = build_code_map_points(str(tmp_path), embed_fn=embed_fn)
        assert len(points) >= 1
        for point in points:
            assert "payload" in point
            assert "vector" in point

    @pytest.mark.asyncio
    async def test_vector_dimension_matches_spec(self, tmp_path: Path):
        from shared.retrieval.index_repo import build_code_map_points
        from shared.embedding import get_embedding_spec
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        spec = get_embedding_spec()
        def embed_fn(text: str) -> list[float]:
            return [0.5] * spec.dim
        points = build_code_map_points(str(tmp_path), embed_fn=embed_fn)
        for point in points:
            assert len(point["vector"]) == spec.dim


class TestVkCacheWiring:
    def test_imports_async_embed(self):
        import importlib
        vk_main = importlib.import_module("vk-cache.server.main")
        assert hasattr(vk_main, "async_embed")

    def test_no_legacy_llama_embed_func(self):
        import importlib
        vk_main = importlib.import_module("vk-cache.server.main")
        assert not hasattr(vk_main, "_llama_embed_func")

    def test_async_embed_is_from_shared(self):
        import importlib
        import shared.embedding as emb
        vk_main = importlib.import_module("vk-cache.server.main")
        assert vk_main.async_embed is emb.async_embed


class TestRankAndFuseContract:
    @pytest.mark.asyncio
    async def test_rank_and_fuse_sorts_by_score(self):
        """_rank_and_fuse sorts items by score when no LLM ranking."""
        from shared.retrieval import _rank_and_fuse, ContextItem, PROFILES
        from shared.llm.config import QueryIntent
        items = {
            "L1": [
                ContextItem(content="low", score=0.3, source_name="L1", source_level=1),
                ContextItem(content="high", score=0.9, source_name="L1", source_level=1),
            ]
        }
        intent = QueryIntent(
            intent_type="debug", entities=[], scope="this_project",
            time_window="all", needs_external=False, needs_ranking=False,
            needs_consolidation=False,
        )
        profile = PROFILES["dev"]
        result = _rank_and_fuse(items, profile, intent)
        assert len(result) == 2
        assert result[0].score >= result[1].score
