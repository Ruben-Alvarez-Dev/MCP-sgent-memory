"""M6: Deterministic entity extraction tests (STO-08)."""
from shared.entity import ENTITY_DICT, extract_entities, infer_entity_type


class TestExtractEntities:
    def test_camelcase_class(self):
        result = extract_entities("AuthService implements JWT authentication")
        names = [e["name"] for e in result]
        assert "AuthService" in names
        assert any(e["type"] == "class" for e in result if e["name"] == "AuthService")

    def test_upper_snake_constant(self):
        result = extract_entities("Use MAX_RETRIES and DATABASE_URL config")
        names = [e["name"] for e in result]
        assert "MAX_RETRIES" in names
        assert "DATABASE_URL" in names

    def test_dictionary_terms(self):
        result = extract_entities("The jwt token authentication failed")
        names = [e["name"] for e in result]
        assert "jwt" in names
        assert "token" in names
        assert "authentication" in names

    def test_spanish_terms(self):
        result = extract_entities("La autenticación con base de datos falló")
        names = [e["name"] for e in result]
        assert "autenticación" in names or "authentication" in names

    def test_deduplication(self):
        result = extract_entities("AuthService and auth service both work")
        names = [e["name"] for e in result]
        assert names.count("AuthService") == 1

    def test_empty_text(self):
        result = extract_entities("")
        assert result == []

    def test_no_entities(self):
        result = extract_entities("the quick brown fox jumps")
        assert all(e["name"] not in {"the", "quick", "brown", "jumps"} for e in result)

    def test_mixed_language(self):
        result = extract_entities("JWT auth con base de datos SQLite")
        names = [e["name"] for e in result]
        assert "jwt" in names
        assert "sqlite" in names or "SQL" in names


class TestInferEntityType:
    def test_camelcase_is_class(self):
        assert infer_entity_type("AuthService") == "class"

    def test_upper_snake_is_module(self):
        # UPPER_SNAKE can be module or constant — both are valid
        assert infer_entity_type("DATABASE_URL") in ("module", "constant")

    def test_lowercase_is_concept(self):
        assert infer_entity_type("authentication") == "concept"


class TestEntityDictionary:
    def test_dict_not_empty(self):
        assert len(ENTITY_DICT) > 20

    def test_spanish_terms_present(self):
        assert "autenticación" in ENTITY_DICT
        assert "base de datos" in ENTITY_DICT
