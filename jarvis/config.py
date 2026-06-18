"""
JARVIS — центральный файл конфигурации.
Содержит все константы и настройки, используемые во всём проекте.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env из корня проекта (на уровень выше jarvis/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ──────────────────────────────────────────────────────────────
# API-ключи (читаются из .env)
# ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
# ──────────────────────────────────────────────────────────────
# Wake word / OpenWakeWord
# ──────────────────────────────────────────────────────────────
WAKE_WORD: str = "hey_jarvis"  # встроенная модель OpenWakeWord (также можно alexa, hey_mycroft)
WAKE_WORD_SENSITIVITY: float = 0.5  # 0.0 — 1.0, выше = чувствительнее

# ──────────────────────────────────────────────────────────────
# Whisper / STT
# ──────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE: str = os.getenv("WHISPER_COMPUTE", "float16")
WHISPER_BEAM_SIZE: int = 5
WHISPER_LANGUAGE: str = "ru"
WHISPER_VAD_FILTER: bool = True

# ──────────────────────────────────────────────────────────────
# OpenRouter API / Brain
# ──────────────────────────────────────────────────────────────
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
OPENROUTER_MAX_TOKENS: int = int(os.getenv("OPENROUTER_MAX_TOKENS", "1024"))
OPENROUTER_STREAM: bool = True

# ──────────────────────────────────────────────────────────────
# Silero TTS
# ──────────────────────────────────────────────────────────────
SILERO_SPEAKER: str = os.getenv("SILERO_SPEAKER", "aidar")
SILERO_SAMPLE_RATE: int = 24000
SILERO_MAX_CHARS: int = 500  # максимум символов на один синтез
SILERO_CACHE_ENABLED: bool = True

# ──────────────────────────────────────────────────────────────
# Диалог / память
# ──────────────────────────────────────────────────────────────
DIALOG_HISTORY_LIMIT: int = 20
LONG_TERM_DB_PATH: Path = _PROJECT_ROOT / "jarvis_memory.db"

# ──────────────────────────────────────────────────────────────
# Аудио / VAD
# ──────────────────────────────────────────────────────────────
SAMPLE_RATE: int = 16000
AUDIO_CHANNELS: int = 1
AUDIO_FORMAT_WIDTH: int = 2  # 16 бит = 2 байта (pyaudio paInt16)

# VAD — энергетический порог (RMS)
SILENCE_THRESHOLD: float = float(os.getenv("SILENCE_THRESHOLD", "0.01"))
SILENCE_DURATION: float = float(os.getenv("SILENCE_DURATION", "1.5"))   # секунд тишины = конец фразы
MAX_RECORD_SECONDS: int = 30   # защита от бесконечной записи
VAD_FRAME_MS: int = 30         # длина кадра для анализа энергии

# ──────────────────────────────────────────────────────────────
# Пути / логирование
# ──────────────────────────────────────────────────────────────
LOG_FILE: Path = _PROJECT_ROOT / "jarvis.log"
LOG_LEVEL: str = os.getenv("JARVIS_LOG_LEVEL", "INFO")

# ──────────────────────────────────────────────────────────────
# Управляющие команды (текстовые)
# ──────────────────────────────────────────────────────────────
CMD_EXIT = ("стоп", "выход", "выключись", "пока")
CMD_CLEAR_HISTORY = ("очисти историю", "забудь", "новый диалог")

# ──────────────────────────────────────────────────────────────
# Приветствие и Безопасность
# ──────────────────────────────────────────────────────────────
GREETING_TEXT: str = "Джарвис активирован. Слушаю, Сэр."
REQUIRE_ACTION_CONFIRMATION: bool = os.getenv("REQUIRE_ACTION_CONFIRMATION", "True").lower() in ("true", "1", "yes")

# ──────────────────────────────────────────────────────────────
# Агентский режим
# ──────────────────────────────────────────────────────────────
AGENT_MAX_TURNS: int = int(os.getenv("AGENT_MAX_TURNS", "7"))  # макс. ходов ReAct-цикла
VOICE_CONFIRM_MAX_SECONDS: int = int(os.getenv("VOICE_CONFIRM_MAX_SECONDS", "5"))  # макс. секунд записи при подтверждении
PLAYWRIGHT_USER_DATA_DIR: Path = _PROJECT_ROOT / os.getenv("PLAYWRIGHT_USER_DATA_DIR", "playwright_profile")


# ──────────────────────────────────────────────────────────────
# Валидация конфигурации
# ──────────────────────────────────────────────────────────────
def validate() -> None:
    """Проверить, что обязательные ключи заданы и не равны шаблонным значениям."""
    errors: list[str] = []

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "sk-or-v1-your-key-here":
        errors.append(
            "OPENROUTER_API_KEY не задан или равен шаблону. "
            "Укажите ключ в .env (получить на https://openrouter.ai)"
        )

    if errors:
        raise ValueError(
            "Ошибки конфигурации:\n" + "\n".join(f"  - {e}" for e in errors)
        )