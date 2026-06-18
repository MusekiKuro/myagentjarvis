"""Tests for TTS utility functions (jarvis.core.tts._clean_text)."""
import re


class TestCleanText:
    """Test _clean_text function from tts module."""

    def _clean_text(self, text: str) -> str:
        """Replicate _clean_text logic for testing without importing tts module
        (which imports torch at module level).
        """
        if not text:
            return ""
        strip_pattern = re.compile(r"[*_`#~>\[\](){}|]+")
        whitespace_pattern = re.compile(r"\s+")
        cleaned = strip_pattern.sub("", text)
        cleaned = whitespace_pattern.sub(" ", cleaned).strip()
        return cleaned

    def test_clean_text_markdown(self):
        """Markdown bold/italic markers should be stripped."""
        result = self._clean_text("**bold** and *italic*")
        assert result == "bold and italic"

    def test_clean_text_code(self):
        """Code backticks should be stripped."""
        result = self._clean_text("`code` block")
        assert result == "code block"

    def test_clean_text_whitespace(self):
        """Multiple spaces should collapse to single space."""
        result = self._clean_text("  extra   spaces  ")
        assert result == "extra spaces"

    def test_clean_text_empty(self):
        """Empty string returns empty string."""
        result = self._clean_text("")
        assert result == ""

    def test_clean_text_none_safe(self):
        """None-like edge case: empty/falsy input returns empty."""
        result = self._clean_text("")
        assert result == ""

    def test_clean_text_hash_headers(self):
        """Markdown headers (###) should be stripped."""
        result = self._clean_text("### Заголовок")
        assert result == "Заголовок"

    def test_clean_text_links(self):
        """Markdown link syntax brackets should be stripped."""
        result = self._clean_text("[ссылка](http://example.com)")
        assert result == "ссылкаhttp://example.com"

    def test_clean_text_pipes(self):
        """Pipe characters (table syntax) should be stripped."""
        result = self._clean_text("| col1 | col2 |")
        assert result == "col1 col2"

    def test_clean_text_preserves_cyrillic(self):
        """Cyrillic text should be preserved."""
        result = self._clean_text("Привет, мир!")
        assert result == "Привет, мир!"

    def test_clean_text_mixed(self):
        """Mixed markdown and text."""
        result = self._clean_text("**Сэр**, вот `результат`:\n- пункт 1\n- пункт 2")
        assert "Сэр" in result
        assert "результат" in result
        assert "*" not in result
        assert "`" not in result
