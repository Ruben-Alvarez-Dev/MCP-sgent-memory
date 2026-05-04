"""Tests for QdrantClient — payload validation and security."""
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared.qdrant_client import _validate_payload_keys, _QDRANT_RESERVED_KEYS


class TestValidatePayloadKeys:
    """Verify that Qdrant payload key validation prevents injection."""

    def test_rejects_reserved_id(self):
        with pytest.raises(ValueError, match="reserved by Qdrant"):
            _validate_payload_keys({"id": "evil", "content": "ok"})

    def test_rejects_reserved_vector(self):
        with pytest.raises(ValueError, match="reserved by Qdrant"):
            _validate_payload_keys({"vector": [1, 2, 3], "content": "ok"})

    def test_rejects_reserved_payload(self):
        with pytest.raises(ValueError, match="reserved by Qdrant"):
            _validate_payload_keys({"payload": {"nested": True}})

    def test_rejects_reserved_sparse_vectors(self):
        with pytest.raises(ValueError, match="reserved by Qdrant"):
            _validate_payload_keys({"sparse_vectors": {"indices": []}})

    def test_rejects_key_with_slash(self):
        with pytest.raises(ValueError, match="must match"):
            _validate_payload_keys({"my/key": "value"})

    def test_rejects_key_with_dot(self):
        with pytest.raises(ValueError, match="must match"):
            _validate_payload_keys({"my.key": "value"})

    def test_rejects_key_starting_with_number(self):
        with pytest.raises(ValueError, match="must match"):
            _validate_payload_keys({"123bad": "value"})

    def test_rejects_key_with_spaces(self):
        with pytest.raises(ValueError, match="must match"):
            _validate_payload_keys({"bad key": "value"})

    def test_accepts_normal_keys(self):
        """Normal alphanumeric keys with underscores should pass."""
        # Should NOT raise
        _validate_payload_keys({
            "memory_id": "abc",
            "content": "hello",
            "layer": "L1",
            "scope_type": "session",
            "created_at": "2025-01-01",
            "_private_key": "ok",
        })

    def test_includes_point_id_in_error(self):
        with pytest.raises(ValueError, match="point-123"):
            _validate_payload_keys({"id": "bad"}, point_id="point-123")

    def test_reserved_keys_set_is_complete(self):
        """Verify the reserved set covers all Qdrant point structure keys."""
        assert "id" in _QDRANT_RESERVED_KEYS
        assert "vector" in _QDRANT_RESERVED_KEYS
        assert "sparse_vectors" in _QDRANT_RESERVED_KEYS
        assert "payload" in _QDRANT_RESERVED_KEYS
