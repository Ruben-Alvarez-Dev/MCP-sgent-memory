"""M6: Synonym query expansion tests (RET-07)."""
from shared.synonym import _SYNONYM_MAP, expand_query


class TestExpandQuery:
    def test_basic_expansion(self):
        result = expand_query("how do we auth users")
        assert "authentication" in result
        assert "jwt" in result
        assert "token" in result
        assert "users" in result

    def test_no_synonym_preserved(self):
        result = expand_query("the quick brown fox")
        assert "quick" in result
        assert "brown" in result

    def test_empty_query(self):
        result = expand_query("")
        assert result == ""

    def test_jwt_expansion(self):
        result = expand_query("jwt authentication")
        assert "json web token" in result

    def test_database_expansion(self):
        result = expand_query("sqlite database")
        assert "sqlite" in result
        assert "postgres" in result or "database" in result

    def test_spanish_expansion(self):
        result = expand_query("autenticación base de datos")
        assert "auth" in result or "authentication" in result


class TestSynonymMap:
    def test_map_not_empty(self):
        assert len(_SYNONYM_MAP) > 20

    def test_bidirectional_coverage(self):
        assert "jwt" in _SYNONYM_MAP.get("auth", "")
        assert "auth" in _SYNONYM_MAP.get("jwt", "")
