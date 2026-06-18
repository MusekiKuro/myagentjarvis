"""
Воспроизведение аудио через sounddevice.
Блокирующее воспроизведение WAV, beep-сигнал, прерывание.
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from typing import Any

import numpy as np

from .. import config

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except ImportError as e:  # pragma: no cover
    sd = None  # type: ignore[assignment]
    logger.warning("sounddevice не установлен: %s", e)


# Состояние воспроизведения — нужно для stop_playback
_playback_lock = threading.Lock()
_current_stream: Any | None = None
_stop_requested = threading.Event()


def play_audio(wav_bytes: bytes) -> None:
    """
    Воспроизвести WAV (16-bit PCM) через системные динамики.
    Блокирующий вызов — ждёт окончания воспроизведения.
    """
    global _current_stream
    if sd is None:
        raise RuntimeError("play_audio: требуется sounddevice")
    if not wav_bytes:
        logger.debug("play_audio: пустые байты — нечего воспроизводить")
        return

    _stop_requested.clear()

    # Парсим WAV
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except wave.Error as e:
        logger.error("play_audio: ошибка парсинга WAV: %s", e)
        return

    if sampwidth == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        logger.error("play_audio: неподдерживаемая ширина сэмпла: %d", sampwidth)
        return

    if channels > 1:
        audio = audio.reshape(-1, channels)

    logger.debug("play_audio: sr=%d, ch=%d, samples=%d", sr, channels, len(audio))

    with _playback_lock:
        try:
            _current_stream = sd.OutputStream(
                samplerate=sr, channels=channels, dtype="float32"
            )
            _current_stream.start()
            # Пишем чанками, чтобы можно было прервать
            chunk_size = 1024
            total = len(audio)
            written = 0
            while written < total and not _stop_requested.is_set():
                end = min(written + chunk_size, total)
                _current_stream.write(audio[written:end])
                written = end
        except Exception as e:
            logger.error("play_audio: ошибка воспроизведения: %s", e)
        finally:
            try:
                if _current_stream is not None:
                    _current_stream.stop()
                    _current_stream.close()
            except Exception:  # pragma: no cover
                pass
            _current_stream = None


def stop_playback() -> None:
    """Прервать текущее воспроизведение (если есть)."""
    logger.info("speaker.stop_playback: запрос на остановку")
    _stop_requested.set()


def play_beep(
    frequency: float = 880.0,
    duration: float = 0.15,
    sample_rate: int | None = None,
) -> None:
    """Короткий звуковой сигнал активации."""
    if sd is None:
        logger.warning("play_beep: sounddevice недоступен")
        return
    sr = sample_rate or 44100
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Плавное затухание, чтобы не было щелчка
    envelope = np.exp(-3.0 * t / duration)
    wave_data = 0.4 * envelope * np.sin(2 * np.pi * frequency * t)
    audio = wave_data.astype(np.float32)
    try:
        sd.play(audio, samplerate=sr, blocking=True)
    except Exception as e:
        logger.error("play_beep: ошибка воспроизведения: %s", e)


def is_playing() -> bool:
    """Активно ли сейчас что-то воспроизводится."""
    with _playback_lock:
        return _current_stream is not None and not _stop_requested.is_set()