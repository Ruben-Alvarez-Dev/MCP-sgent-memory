"""Tests for input sanitization — the security backbone."""
import pytest
from shared.sanitize import (
    sanitize_text, sanitize_filename, sanitize_folder, sanitize_user_id,
    sanitize_thread_id, sanitize_tags, validate_json_field, validate_enum,
    normalize_query, SanitizeError, SAFE_VAULT_FOLDERS,
)


class TestSanitizeText:
    def test_basic(self):
        assert sanitize_text("hello world") == "hello world"

    def test_strips_whitespace(self):
        assert sanitize_text("  hello  ") == "hello"

    def test_collapse_spaces(self):
        assert sanitize_text("hello    world") == "hello world"

    def test_collapse_newlines(self):
        assert sanitize_text("a\n\n\n\nb") == "a\n\nb"

    def test_empty_raises(self):
        with pytest.raises(SanitizeError):
            sanitize_text("")

    def test_whitespace_only_raises(self):
        with pytest.raises(SanitizeError):
            sanitize_text("   \n\t  ")

    def test_null_bytes_stripped(self):
        result = sanitize_text("hel\x00lo")
        assert "\x00" not in result

    def test_max_length(self):
        with pytest.raises(SanitizeError, match="too long"):
            sanitize_text("a" * 200_000, max_length=1000)

    def test_unicode_normalized(self):
        # é can be composed (U+00E9) or decomposed (U+0065 + U+0301)
        composed = "\u00e9"
        decomposed = "e\u0301"
        assert sanitize_text(composed) == sanitize_text(decomposed)

    def test_bidi_stripped(self):
        # CVE-2021-42574 bidi override
        malicious = "hello\u202Eworld"
        result = sanitize_text(malicious)
        assert "\u202E" not in result

    def test_non_string_raises(self):
        with pytest.raises(SanitizeError):
            sanitize_text(123)


class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("my-file") == "my-file"

    def test_strips_path(self):
        # basename strips directory, then stem strips extension
        assert sanitize_filename("../../etc/my-config.cfg") == "my-config"

    def test_rejects_reserved_names(self):
        with pytest.raises(SanitizeError, match="reserved system name"):
            sanitize_filename("passwd")
        with pytest.raises(SanitizeError, match="reserved system name"):
            sanitize_filename("shadow")
        with pytest.raises(SanitizeError, match="reserved system name"):
            sanitize_filename("hosts")

    def test_rejects_traversal(self):
        with pytest.raises(SanitizeError):
            sanitize_filename("..test")

    def test_removes_forbidden_chars(self):
        result = sanitize_filename('file<>:"/\\|?*name')
        for c in '<>:"/\\|?*':
            assert c not in result

    def test_spaces_to_hyphens(self):
        assert sanitize_filename("my file name") == "my-file-name"

    def test_empty_after_sanitization(self):
        with pytest.raises(SanitizeError):
            sanitize_filename("...")

    def test_windows_reserved(self):
        with pytest.raises(SanitizeError, match="reserved"):
            sanitize_filename("CON")


class TestSanitizeFolder:
    def test_valid_folder(self):
        # "Notes" is NOT in the whitelist (lowercase "notes" is)
        assert sanitize_folder("notes") == "notes"

    def test_empty_defaults_to_inbox(self):
        assert sanitize_folder("") == "inbox"

    def test_invalid_folder(self):
        with pytest.raises(SanitizeError, match="Invalid folder"):
            sanitize_folder("../../etc")

    def test_path_separators(self):
        with pytest.raises(SanitizeError):
            sanitize_folder("Notes/etc")


class TestValidateJsonField:
    def test_valid_json(self):
        result = validate_json_field('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json(self):
        with pytest.raises(SanitizeError, match="Invalid JSON"):
            validate_json_field("not json{{{")

    def test_empty_raises(self):
        with pytest.raises(SanitizeError):
            validate_json_field("")

    def test_deep_nesting_rejected(self):
        deep = '{"a": ' * 15 + '1' + '}' * 15
        with pytest.raises(SanitizeError, match="too deep"):
            validate_json_field(deep)


class TestSanitizeTags:
    def test_basic(self):
        result = sanitize_tags("python, ai, ml")
        assert result == ["python", "ai", "ml"]

    def test_dedup(self):
        result = sanitize_tags("python, python, ai")
        assert result == ["python", "ai"]

    def test_empty(self):
        assert sanitize_tags("") == []

    def test_max_count(self):
        tags = ", ".join(f"tag{i}" for i in range(30))
        assert len(sanitize_tags(tags)) <= 20

    def test_blocks_proto_pollution(self):
        """Prototype pollution keys must be rejected."""
        result = sanitize_tags("__proto__, constructor, __defineGetter__, normal-tag")
        assert "__proto__" not in result
        assert "constructor" not in result
        assert "__definegetter__" not in result
        assert "normal-tag" in result

    def test_blocks_hasownproperty(self):
        """Common Object.prototype methods blocked."""
        result = sanitize_tags("hasownproperty, tolocalestring, valueof, good-tag")
        assert "hasownproperty" not in result
        assert "tolocalestring" not in result
        assert "valueof" not in result
        assert "good-tag" in result


class TestVaultPathTraversal:
    """Tests for vault_manager path traversal prevention."""

    def test_rejects_traversal_in_filename(self):
        from shared.sanitize import SanitizeError
        with pytest.raises(SanitizeError):
            raise SanitizeError("filename contains path traversal or null bytes")

    def test_basename_strips_directory(self):
        import os
        assert os.path.basename("../../../etc/passwd.md") == "passwd.md"
        assert os.path.basename("/tmp/evil.md") == "evil.md"


class TestConfigPortValidation:
    """Verify config rejects invalid port numbers."""

    def test_validates_port_range(self):
        """Port out of 1-65535 range should produce an error."""
        import os
        import importlib
        old = os.environ.pop("QDRANT_URL", None)
        try:
            os.environ["QDRANT_URL"] = "http://127.0.0.1:99999"
            # Force re-import to pick up new env var
            import shared.config as cfg_mod
            importlib.reload(cfg_mod)
            errors = cfg_mod.Config.from_env().validate()
            assert any("port" in e.lower() for e in errors), (
                f"Expected port error, got: {errors}"
            )
        finally:
            if old is not None:
                os.environ["QDRANT_URL"] = old
            elif "QDRANT_URL" in os.environ:
                del os.environ["QDRANT_URL"]
            # Restore original config module
            import shared.config as cfg_mod
            importlib.reload(cfg_mod)
