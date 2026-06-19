"""
Speech-to-Text через faster-whisper.
Загружает модель один раз на GPU (CUDA), затем транскрибирует аудио.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from .. import config

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
except ImportError as e:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]
    logger.warning(
        "faster-whisper не установлен: %s. Установите: pip install faster-whisper",
        e,
    )


class SpeechToText:
    """Обёртка над faster-whisper с авто-fallback на CPU."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        if WhisperModel is None:
            raise RuntimeError(
                "SpeechToText: требуется faster-whisper. "
                "Установите: pip install faster-whisper"
            )

        self._model_size = model_size or config.WHISPER_MODEL
        requested_device = device or config.WHISPER_DEVICE
        requested_compute = compute_type or config.WHISPER_COMPUTE

        self._device, self._compute_type = self._resolve_device(
            requested_device, requested_compute
        )

        logger.info(
            "SpeechToText: загружаю модель '%s' на %s (%s)...",
            self._model_size,
            self._device,
            self._compute_type,
        )
        try:
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception as e:
            if self._device == "cuda":
                logger.warning(
                    "SpeechToText: CUDA недоступна (%s) — переключаюсь на CPU int8",
                    e,
                )
                self._device = "cpu"
                self._compute_type = "int8"
                self._model = WhisperModel(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                )
            else:
                raise

        logger.info(
            "SpeechToText: готово (device=%s, compute_type=%s)",
            self._device,
            self._compute_type,
        )

    @staticmethod
    def _resolve_device(device: str, compute_type: str) -> tuple[str, str]:
        """Проверить доступность CUDA, иначе fallback на CPU."""
        if device != "cuda":
            return device, compute_type
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning(
                    "SpeechToText: CUDA недоступна в системе — переключаюсь на CPU"
                )
                return "cpu", "int8"
        except ImportError:
            logger.warning("SpeechToText: torch не установлен — fallback на CPU")
            return "cpu", "int8"
        return device, compute_type

    def transcribe(self, audio_np: np.ndarray) -> str:
        """
        Распознать аудио (float32, sample_rate=16000) → строка текста.
        Параметры: language='ru', beam_size=5, vad_filter=True.
        """
        if audio_np is None or len(audio_np) == 0:
            logger.debug("SpeechToText.transcribe: пустое аудио")
            return ""

        # faster-whisper ожидает numpy float32 с shape (n,) или (1, n)
        if audio_np.dtype != np.float32:
            audio_np = audio_np.astype(np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.flatten()

        t0 = time.perf_counter()
        try:
            segments, info = self._model.transcribe(
                audio_np,
                language=config.WHISPER_LANGUAGE,
                beam_size=config.WHISPER_BEAM_SIZE,
                vad_filter=config.WHISPER_VAD_FILTER,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            elapsed = time.perf_counter() - t0
            logger.info(
                "SpeechToText: %.2f сек, lang=%s, prob=%.2f, текст: %r",
                elapsed,
                info.language,
                info.language_probability,
                text[:120],
            )
            return text
        except Exception as e:
            logger.error("SpeechToText: ошибка транскрибации: %s", e)
            return ""

    @property
    def device(self) -> str:
        return self._device

    @property
    def compute_type(self) -> str:
        return self._compute_type
