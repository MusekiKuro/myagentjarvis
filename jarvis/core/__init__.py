"""Пакет core — модули голосового ввода/вывода и ИИ."""

from .brain import Brain
from .listener import WakeWordListener, record_until_silence
from .speaker import is_playing, play_audio, play_beep, stop_playback
from .stt import SpeechToText
from .tts import TextToSpeech

__all__ = [
    "Brain",
    "SpeechToText",
    "TextToSpeech",
    "WakeWordListener",
    "is_playing",
    "play_audio",
    "play_beep",
    "record_until_silence",
    "stop_playback",
]
