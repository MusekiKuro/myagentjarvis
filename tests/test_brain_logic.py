"""Tests for Brain logic WITHOUT actual API calls."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.memory.short_term import ShortTermMemory


class TestHandleApiError:
    """Test Brain._handle_api_error error classification."""

    def _make_brain_instance(self):
        """Create a Brain instance."""
        from jarvis.core.brain import Brain
        with patch.object(Brain, "__init__", lambda self, **kw: None):
            brain = Brain.__new__(Brain)
            brain._short_term = ShortTermMemory(limit=10)
            brain._model = "google/gemma-4-31b-it:free"
            brain._max_tokens = 500
            brain._api_key = "sk-or-v1-test-key"
            return brain

    def test_handle_api_error_auth(self):
        """401/auth errors should mention ключ недействителен."""
        brain = self._make_brain_instance()
        result = brain._handle_api_error(Exception("401 Unauthorized"))
        assert "ключ" in result.lower() or "api" in result.lower()

    def test_handle_api_error_rate(self):
        """429/rate limit errors should mention слишком много запросов."""
        brain = self._make_brain_instance()
        result = brain._handle_api_error(Exception("429 Too Many Requests"))
        assert "много запросов" in result.lower() or "подождите" in result.lower()

    def test_handle_api_error_timeout(self):
        """Timeout errors should mention нет связи."""
        brain = self._make_brain_instance()
        result = brain._handle_api_error(Exception("Connection timed out"))
        assert "связи" in result.lower() or "интернет" in result.lower()

    def test_handle_api_error_generic(self):
        """Unknown errors should return generic error message."""
        brain = self._make_brain_instance()
        result = brain._handle_api_error(Exception("Something weird happened"))
        assert "сэр" in result.lower()
        assert "ответ" in result.lower() or "сервер" in result.lower()


class TestBuildSystemPrompt:
    """Test Brain._build_system_prompt."""

    def _make_brain_instance(self):
        """Create a Brain instance."""
        from jarvis.core.brain import Brain
        with patch.object(Brain, "__init__", lambda self, **kw: None):
            brain = Brain.__new__(Brain)
            brain._short_term = ShortTermMemory(limit=10)
            brain._model = "google/gemma-4-31b-it:free"
            brain._max_tokens = 500
            brain._api_key = "sk-or-v1-test-key"
            return brain

    def test_build_system_prompt_no_context(self):
        """Without long-term context, returns base SYSTEM_PROMPT."""
        from jarvis.core.brain import SYSTEM_PROMPT

        brain = self._make_brain_instance()
        result = brain._build_system_prompt()
        assert result == SYSTEM_PROMPT

    def test_build_system_prompt_with_context(self):
        """With long-term context, appends it to SYSTEM_PROMPT."""
        from jarvis.core.brain import SYSTEM_PROMPT

        brain = self._make_brain_instance()
        context = "Имя пользователя: Алексей"
        result = brain._build_system_prompt(context)
        assert SYSTEM_PROMPT in result
        assert context in result
        assert result == f"{SYSTEM_PROMPT}\n\n{context}"


class TestGetResponseEdgeCases:
    """Test Brain.get_response edge cases."""

    def _make_brain_instance(self):
        """Create a Brain instance."""
        from jarvis.core.brain import Brain
        with patch.object(Brain, "__init__", lambda self, **kw: None):
            brain = Brain.__new__(Brain)
            brain._short_term = ShortTermMemory(limit=10)
            brain._model = "google/gemma-4-31b-it:free"
            brain._max_tokens = 500
            brain._api_key = "sk-or-v1-test-key"
            return brain

    def test_get_response_empty_text(self):
        """Empty string should return empty string without API call."""
        brain = self._make_brain_instance()
        with patch("requests.post") as mock_post:
            result = brain.get_response("")
            assert result == ""
            mock_post.assert_not_called()

    def test_get_response_whitespace_only(self):
        """Whitespace-only string should return empty string."""
        brain = self._make_brain_instance()
        with patch("requests.post") as mock_post:
            result = brain.get_response("   ")
            assert result == ""
            mock_post.assert_not_called()
