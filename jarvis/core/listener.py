"""
Прослушивание wake word и запись речи пользователя.
Использует Porcupine для детекции 'джарвис' без нагрузки на CPU.
После активации пишет аудио с микрофона, пока пользователь говорит
(простой VAD через энергетический порог).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .. import config

logger = logging.getLogger(__name__)

try:
    import openwakeword
    import pyaudio
    from openwakeword.model import Model
except ImportError as e:  # pragma: no cover
    pyaudio = None  # type: ignore[assignment]
    openwakeword = None  # type: ignore[assignment]
    Model = None  # type: ignore[assignment]
    logger.warning(
        "Не найдены pyaudio/openwakeword: %s. Установите зависимости из requirements.txt",
        e,
    )


# ──────────────────────────────────────────────────────────────
# Хелперы для преобразования аудио
# ──────────────────────────────────────────────────────────────
def _audio_int16_to_float32(raw: bytes) -> np.ndarray:
    """Преобразовать сырой int16 PCM в numpy float32 [-1, 1]."""
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return samples
    return samples / 32768.0


def _rms_energy(audio: np.ndarray) -> float:
    """RMS энергия сигнала — простой proxy для громкости (для VAD)."""
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))


# ──────────────────────────────────────────────────────────────
# Wake word
# ──────────────────────────────────────────────────────────────
class WakeWordListener:
    """
    Постоянно слушает микрофон и ждёт wake word 'hey_jarvis' (или другой).
    Использует OpenWakeWord — лёгкий локальный детектор.
    """

    def __init__(
        self,
        keyword: str | None = None,
        sensitivity: float | None = None,
    ) -> None:
        if openwakeword is None or pyaudio is None or Model is None:
            raise RuntimeError(
                "WakeWordListener: требуются pyaudio и openwakeword. "
                "Установите: pip install pyaudio openwakeword"
            )

        self._keyword = keyword or config.WAKE_WORD
        self._sensitivity = (
            sensitivity if sensitivity is not None else config.WAKE_WORD_SENSITIVITY
        )

        try:
            # Загружаем модель (OWW сам скачивает встроенные модели, если их нет в кэше, но hey_jarvis обычно идет в комплекте)
            self._oww_model = Model(wakeword_models=[self._keyword], inference_framework="onnx")
        except Exception as e:
            logger.error("WakeWordListener: не удалось создать OpenWakeWord Model: %s", e)
            raise

        self._pa = pyaudio.PyAudio()
        self._stream: Any | None = None

        # OWW всегда работает с 16000 Hz, 1 channel, 16-bit PCM
        self.sample_rate = 16000
        # OWW ожидает фреймы определенного размера (обычно 1280 сэмплов = 80ms)
        self.frame_length = 1280

        logger.info(
            "WakeWordListener: инициализирован (keyword=%s, sensitivity=%.2f, rate=%d)",
            self._keyword,
            self._sensitivity,
            self.sample_rate,
        )

    def _open_stream(self) -> Any:
        return self._pa.open(
            rate=self.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.frame_length,
        )

    def listen(self) -> bool:
        """
        Блокирующий цикл: слушает микрофон, возвращает True при обнаружении wake word.
        Безопасно прерывается через KeyboardInterrupt.
        """
        if self._stream is None:
            self._stream = self._open_stream()

        # Сбрасываем внутреннее состояние модели OWW, чтобы забыть старые предсказания
        try:
            self._oww_model.reset()
        except Exception as e:
            logger.warning("WakeWordListener: не удалось сбросить OWW модель: %s", e)

        # Перезапускаем поток, чтобы очистить буферы PortAudio от старого звука (например, от воспроизведения TTS)
        try:
            if not self._stream.is_stopped():
                self._stream.stop_stream()
            self._stream.start_stream()
        except Exception as e:
            logger.error("WakeWordListener: ошибка перезапуска потока: %s", e)
            raise

        logger.info("WakeWordListener: ожидаю wake word '%s'...", self._keyword)
        try:
            while True:
                pcm = self._stream.read(
                    self.frame_length,
                    exception_on_overflow=False,
                )

                # Передаем аудио фрейм в OWW
                audio_array = np.frombuffer(pcm, dtype=np.int16)
                prediction = self._oww_model.predict(audio_array)

                for model_name, score in prediction.items():
                    if score >= self._sensitivity:
                        logger.info(
                            "WakeWordListener: wake word '%s' обнаружен (score=%.2f)", model_name, score
                        )
                        # Останавливаем поток, чтобы он не копил звук во время обработки и озвучки ответа
                        try:
                            self._stream.stop_stream()
                        except Exception as stop_err:
                            logger.warning("WakeWordListener: не удалось остановить поток: %s", stop_err)
                        return True
        except KeyboardInterrupt:
            logger.info("WakeWordListener: прервано пользователем")
            try:
                if self._stream and not self._stream.is_stopped():
                    self._stream.stop_stream()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error("WakeWordListener: ошибка в цикле прослушивания: %s", e)
            try:
                if self._stream and not self._stream.is_stopped():
                    self._stream.stop_stream()
            except Exception:
                pass
            raise

    def close(self) -> None:
        """Корректно освободить ресурсы."""
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        except Exception as e:  # pragma: no cover
            logger.warning("WakeWordListener: ошибка закрытия потока: %s", e)
        try:
            self._pa.terminate()
        except Exception as e:  # pragma: no cover
            logger.warning("WakeWordListener: ошибка terminate PyAudio: %s", e)

    def __enter__(self) -> WakeWordListener:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ──────────────────────────────────────────────────────────────
# Запись после wake word (с VAD)
# ──────────────────────────────────────────────────────────────
def record_until_silence(
    silence_threshold: float | None = None,
    silence_duration: float | None = None,
    sample_rate: int | None = None,
    max_seconds: int | None = None,
    pa: pyaudio.PyAudio | None = None,
) -> np.ndarray:
    """
    Записывает аудио с микрофона, пока пользователь говорит.
    Останавливается, когда silence_duration секунд подряд тишина
    (RMS < silence_threshold). Возвращает float32 numpy array, sample_rate=16000.
    """
    if pyaudio is None:
        raise RuntimeError("record_until_silence: требуется pyaudio")

    sr = sample_rate or config.SAMPLE_RATE
    threshold = (
        silence_threshold if silence_threshold is not None else config.SILENCE_THRESHOLD
    )
    silence_sec = (
        silence_duration if silence_duration is not None else config.SILENCE_DURATION
    )
    max_sec = max_seconds or config.MAX_RECORD_SECONDS

    own_pa = pa is None
    if own_pa:
        pa = pyaudio.PyAudio()
    frames_per_buffer = max(
        1, int(sr * config.VAD_FRAME_MS / 1000.0)
    )
    silence_frames_needed = max(1, int(silence_sec * 1000 / config.VAD_FRAME_MS))
    max_frames = max(1, int(max_sec * 1000 / config.VAD_FRAME_MS))

    stream = pa.open(
        rate=sr,
        channels=config.AUDIO_CHANNELS,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=frames_per_buffer,
    )

    frames: list[bytes] = []
    silence_counter = 0
    speech_detected = False

    logger.debug(
        "record_until_silence: начало записи (sr=%d, threshold=%.4f, silence=%.1fs)",
        sr,
        threshold,
        silence_sec,
    )

    pre_roll: list[bytes] = []
    pre_roll_limit = 6  # Сохраняем ~180мс до начала речи (при VAD_FRAME_MS = 30)

    try:
        for _ in range(max_frames):
            raw = stream.read(frames_per_buffer, exception_on_overflow=False)
            audio = _audio_int16_to_float32(raw)
            energy = _rms_energy(audio)

            if energy >= threshold:
                if not speech_detected:
                    speech_detected = True
                    # Добавляем накопленный pre-roll буфер, чтобы не резать начало фразы
                    frames.extend(pre_roll)
                    pre_roll.clear()
                silence_counter = 0
                frames.append(raw)
            else:
                if speech_detected:
                    frames.append(raw)
                    silence_counter += 1
                    if silence_counter >= silence_frames_needed:
                        logger.debug(
                            "record_until_silence: тишина %d фреймов — конец записи",
                            silence_counter,
                        )
                        break
                else:
                    pre_roll.append(raw)
                    if len(pre_roll) > pre_roll_limit:
                        pre_roll.pop(0)
    finally:
        stream.stop_stream()
        stream.close()
        if own_pa:
            pa.terminate()

    if not frames:
        logger.debug("record_until_silence: речь не обнаружена")
        return np.zeros(0, dtype=np.float32)

    audio_int16 = np.frombuffer(b"".join(frames), dtype=np.int16)
    audio_float = audio_int16.astype(np.float32) / 32768.0
    duration = len(audio_float) / sr
    logger.info(
        "record_until_silence: записано %.2f сек (%d сэмплов)",
        duration,
        len(audio_float),
    )
    return audio_float
