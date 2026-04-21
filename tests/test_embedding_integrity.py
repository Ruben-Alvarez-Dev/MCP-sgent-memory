"""Tests for shared.embedding — pipeline, spec, validation, wiring.

Covers: EMBEDDING_DIM constant, NoOpBackend, validation, EmbeddingSpec
immutability, retrieval delegation, code map vector generation, and
vk-cache wiring.
"""

from __future__ import annotations

import pytest

from shared.embedding import (
    EMBEDDING_DIM,
    EmbeddingSpec,
    NoOpBackend,
    _validate_embedding_vector,
    get_embedding_spec,
)


# ── Embedding pipeline ────────────────────────────────────────────


class TestEmbeddingPipeline:
    def test_dim_is_1024(self):
        assert EMBEDDING_DIM == 1024

    def test_noop_backend_produces_zero_vector_of_correct_dim(self):
        vec = NoOpBackend().embed("anything")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vec)

    def test_validation_rejects_wrong_dimension(self):
        spec = get_embedding_spec()
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            _validate_embedding_vector([0.1] * 384, spec)

    def test_validation_accepts_correct_dimension(self):
        spec = get_embedding_spec()
        vec = [0.1] * spec.dim
        assert _validate_embedding_vector(vec, spec) is vec

    def test_validation_rejects_empty_vector(self):
        with pytest.raises(RuntimeError, match="empty or invalid"):
            _validate_embedding_vector([], get_embedding_spec())


# ── EmbeddingSpec contract ────────────────────────────────────────


class TestEmbeddingSpec:
    def test_spec_is_frozen(self):
        spec = EmbeddingSpec(
            backend="llama_cpp", model_id="bge-m3", dim=1024,
            metric="cosine", version="v1",
        )
        with pytest.raises(AttributeError):
            spec.dim = 384

    def test_key_has_five_colon_parts(self):
        key = get_embedding_spec().key
        parts = key.split(":")
        assert len(parts) == 5
        assert parts[2].isdigit()

    def test_default_spec_values(self):
        spec = get_embedding_spec()
        assert spec.dim == 1024
        assert spec.metric == "cosine"


# ── Retrieval delegation ──────────────────────────────────────────


class TestRetrievalDelegation:
    def test_retrieval_uses_shared_embedding(self):
        import shared.retrieval as retrieval_mod
        import shared.embedding as embedding_mod
        assert retrieval_mod.get_embedding is embedding_mod.get_embedding

    def test_classify_intent_returns_QueryIntent(self):
        from shared.retrieval import classify_intent
        from shared.llm.config import QueryIntent

        intent = classify_intent("where is the AuthService class defined?")
        assert isinstance(intent, QueryIntent)
        assert intent.intent_type == "code_lookup"
        assert intent.scope == "this_project"

    def test_prune_content_truncates_long_input(self):
        from shared.retrieval import prune_content
        source = "def alpha():\n    x = 1\n    return x\n\ndef beta():\n    return 'ok'\n"
        result = prune_content(source, path="test.py", max_tokens=3)
        assert len(result) < len(source)

    def test_prune_content_passthrough_when_fits(self):
        from shared.retrieval import prune_content
        assert prune_content("hello", max_tokens=100) == "hello"


# ── Qdrant payload integrity ─────────────────────────────────────


class TestQdrantPayload:
    def test_code_map_points_include_payload_and_vector(self, tmp_path, noop_embed):
        from shared.retrieval.index_repo import build_code_map_points
        (tmp_path / "example.py").write_text("def hello():\n    return 'world'\n")
        points = build_code_map_points(str(tmp_path), embed_fn=noop_embed)
        assert len(points) >= 1
        for p in points:
            assert "payload" in p
            assert "vector" in p
            assert len(p["vector"]) == EMBEDDING_DIM

    def test_vector_dim_matches_spec(self, tmp_path, noop_embed):
        from shared.retrieval.index_repo import build_code_map_points
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        points = build_code_map_points(str(tmp_path), embed_fn=noop_embed)
        for p in points:
            assert len(p["vector"]) == get_embedding_spec().dim


# ── vk-cache wiring ───────────────────────────────────────────────


class TestVkCacheWiring:
    def test_vk_cache_imports_async_embed(self):
        import importlib
        vk = importlib.import_module("vk-cache.server.main")
        assert hasattr(vk, "async_embed")

    def test_no_legacy_llama_embed_func(self):
        import importlib
        vk = importlib.import_module("vk-cache.server.main")
        assert not hasattr(vk, "_llama_embed_func")

    def test_async_embed_is_from_shared(self):
        import importlib
        import shared.embedding as emb
        vk = importlib.import_module("vk-cache.server.main")
        assert vk.async_embed is emb.async_embed


# ── _rank_and_fuse contract ──────────────────────────────────────


class TestRankAndFuse:
    def test_sorts_by_score(self):
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
        result = _rank_and_fuse(items, PROFILES["dev"], intent)
        assert len(result) == 2
        assert result[0].score >= result[1].score
