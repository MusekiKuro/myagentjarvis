"""Tests for config validation logic."""
import os
import pytest
from unittest.mock import patch


class TestConfigValidation:
    """Test validation of API keys from environment."""

    def _validate_keys(self, env_vars: dict):
        """Simulate config validation logic matching what Brain and WakeWordListener do."""
        openrouter_key = env_vars.get("OPENROUTER_API_KEY", "")

        errors = []

        if not openrouter_key:
            errors.append(
                "OPENROUTER_API_KEY не задан. "
                "Укажите ключ в .env"
            )
        elif openrouter_key == "sk-or-v1-your-key-here":
            errors.append(
                "OPENROUTER_API_KEY равен шаблону. "
                "Укажите настоящий ключ в .env"
            )

        if errors:
            raise ValueError("; ".join(errors))

    def test_validate_missing_openrouter_key(self):
        """Missing OPENROUTER_API_KEY should raise ValueError."""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            self._validate_keys({})

    def test_validate_template_openrouter_key(self):
        """Template OPENROUTER_API_KEY should raise ValueError."""
        with pytest.raises(ValueError, match="шаблон"):
            self._validate_keys({
                "OPENROUTER_API_KEY": "sk-or-v1-your-key-here",
            })

    def test_validate_valid_keys(self):
        """Valid keys should not raise any error."""
        # Should not raise
        self._validate_keys({
            "OPENROUTER_API_KEY": "sk-or-v1-real-key-abc123",
        })


class TestConfigConstants:
    """Test that config module loads expected constant values."""

    def test_dialog_history_limit(self):
        """DIALOG_HISTORY_LIMIT should be a positive integer."""
        from jarvis import config

        assert isinstance(config.DIALOG_HISTORY_LIMIT, int)
        assert config.DIALOG_HISTORY_LIMIT > 0

    def test_sample_rate(self):
        """SAMPLE_RATE should be 16000."""
        from jarvis import config

        assert config.SAMPLE_RATE == 16000

    def test_audio_channels(self):
        """AUDIO_CHANNELS should be 1 (mono)."""
        from jarvis import config

        assert config.AUDIO_CHANNELS == 1

    def test_silero_sample_rate(self):
        """SILERO_SAMPLE_RATE should be 24000."""
        from jarvis import config

        assert config.SILERO_SAMPLE_RATE == 24000

    def test_openrouter_model_set(self):
        """OPENROUTER_MODEL should be set to a non-empty string."""
        from jarvis import config

        assert isinstance(config.OPENROUTER_MODEL, str)
        assert len(config.OPENROUTER_MODEL) > 0

    def test_wake_word(self):
        """WAKE_WORD should be 'hey_jarvis'."""
        from jarvis import config

        assert config.WAKE_WORD == "hey_jarvis"
