"""Shared fixtures for JARVIS tests."""
import os
import sys
from unittest.mock import MagicMock
import pytest

# Ensure test environment doesn't use real keys
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-v1-test-key-for-testing")

# Mock heavy/hardware dependencies before anything from jarvis is imported
sys.modules['torch'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['openwakeword'] = MagicMock()
sys.modules['openwakeword.model'] = MagicMock()
sys.modules['pyaudio'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()

# Add project root to path so jarvis package is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary SQLite database path."""
    return tmp_path / "test_memory.db"


@pytest.fixture
def short_term():
    """Fresh ShortTermMemory instance."""
    from jarvis.memory.short_term import ShortTermMemory

    return ShortTermMemory(limit=10)


@pytest.fixture
def long_term(tmp_db):
    """Fresh LongTermMemory with temp database."""
    from jarvis.memory.long_term import LongTermMemory

    mem = LongTermMemory(db_path=tmp_db)
    yield mem
    mem.close()
