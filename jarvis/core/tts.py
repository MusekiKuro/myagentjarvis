"""
Text-to-Speech через Silero TTS (локально, без интернета).
Загружается один раз через torch.hub.load.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import wave
from collections import OrderedDict
from typing import Any

import numpy as np
import torch

from .. import config

logger = logging.getLogger(__name__)


# Markdown/спец-символы, которые плохо звучат через TTS
_STRIP_PATTERN = re.compile(r"[*_`#~>\[\](){}|]+")
# Множественные пробелы и переносы
_WHITESPACE_PATTERN = re.compile(r"\s+")

# LRU-кэш: лимиты
_CACHE_MAX_ENTRIES = 100
_CACHE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _clean_text(text: str) -> str:
    """Убрать markdown-разметку и лишние пробелы перед синтезом."""
    if not text:
        return ""
    cleaned = _STRIP_PATTERN.sub("", text)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned


class TextToSpeech:
    """Обёртка над Silero TTS с LRU-кэшем частых фраз."""

    # Предзаполненный кэш для типичных ответов
    DEFAULT_CACHE: dict[str, bytes] = {}

    def __init__(
        self,
        speaker: str | None = None,
        sample_rate: int | None = None,
    ) -> None:
        self._speaker = speaker or config.SILERO_SPEAKER
        self._sample_rate = sample_rate or config.SILERO_SAMPLE_RATE
        self._model: Any | None = None
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_total_bytes: int = 0
        self._cache_lock = threading.Lock()

        # Предзаполняем из DEFAULT_CACHE
        for k, v in self.DEFAULT_CACHE.items():
            self._cache[k] = v
            self._cache_total_bytes += len(v)

        logger.info(
            "TextToSpeech: загружаю Silero v3_1_ru (speaker=%s, sr=%d)...",
            self._speaker,
            self._sample_rate,
        )
        try:
            self._model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker="v3_1_ru",
            )
            self._model.to(torch.device("cpu"))  # Silero CPU-only
        except Exception as e:
            logger.error("TextToSpeech: не удалось загрузить Silero: %s", e)
            raise

        logger.info("TextToSpeech: готово (speaker=%s)", self._speaker)

    # ──────────────────────────────────────────────────────────
    # LRU-кэш helpers
    # ──────────────────────────────────────────────────────────
    def _cache_put(self, key: str, value: bytes) -> None:
        """Добавить в LRU-кэш (вызывать под _cache_lock)."""
        if key in self._cache:
            # Обновляем: убираем старый размер, перезаписываем
            self._cache_total_bytes -= len(self._cache[key])
            self._cache[key] = value
            self._cache.move_to_end(key)
            self._cache_total_bytes += len(value)
        else:
            self._cache[key] = value
            self._cache_total_bytes += len(value)

        # Вытесняем старые записи, пока превышены лимиты
        while (
            len(self._cache) > _CACHE_MAX_ENTRIES
            or self._cache_total_bytes > _CACHE_MAX_BYTES
        ):
            if not self._cache:
                break
            evicted_key, evicted_val = self._cache.popitem(last=False)
            self._cache_total_bytes -= len(evicted_val)
            logger.debug("TextToSpeech: cache evict %r (%d bytes)", evicted_key[:40], len(evicted_val))

    def _cache_get(self, key: str) -> bytes | None:
        """Получить из LRU-кэша с обновлением позиции (вызывать под _cache_lock)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    # ──────────────────────────────────────────────────────────
    # Синтез
    # ──────────────────────────────────────────────────────────
    def synthesize(self, text: str) -> bytes:
        """
        Синтез текста → WAV bytes (16-bit PCM mono).
        Возвращает bytes — готовые данные для sounddevice.
        """
        if not text or not text.strip():
            return b""

        cleaned = _clean_text(text)
        if not cleaned:
            return b""

        # Кэш — проверка
        if config.SILERO_CACHE_ENABLED:
            with self._cache_lock:
                cached = self._cache_get(cleaned)
                if cached is not None:
                    logger.debug("TextToSpeech: cache hit for %r", cleaned[:60])
                    return cached

        # Silero имеет внутренний лимит ~1000 символов — режем безопаснее
        chunks = self._split_long_text(cleaned)
        wavs: list[bytes] = []
        for chunk in chunks:
            try:
                wavs.append(self._synth_one(chunk))
            except Exception as e:
                logger.error("TextToSpeech: ошибка синтеза чанка: %s", e)
                continue

        if not wavs:
            return b""

        result = self._concat_wavs(wavs) if len(wavs) > 1 else wavs[0]

        # Кэш — сохранение
        if config.SILERO_CACHE_ENABLED:
            with self._cache_lock:
                self._cache_put(cleaned, result)

        return result

    def _synth_one(self, text: str) -> bytes:
        """Один вызов Silero для одного чанка."""
        assert self._model is not None
        audio_tensor = self._model.apply_tts(
            text=text,
            speaker=self._speaker,
            sample_rate=self._sample_rate,
        )
        # audio_tensor — torch.Tensor float32 в диапазоне [-1, 1]
        audio_np = audio_tensor.cpu().numpy().astype(np.float32)
        return self._to_wav_bytes(audio_np)

    def _split_long_text(self, text: str) -> list[str]:
        """Разбить длинный текст на части ≤ SILERO_MAX_CHARS по предложениям."""
        if len(text) <= config.SILERO_MAX_CHARS:
            return [text]

        # Режем по границам предложений
        parts: list[str] = []
        current = ""
        # Простая сегментация по . ! ? и запятой, если предложение слишком длинное
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sent in sentences:
            if len(current) + len(sent) + 1 <= config.SILERO_MAX_CHARS:
                current = (current + " " + sent).strip()
            else:
                if current:
                    parts.append(current)
                if len(sent) > config.SILERO_MAX_CHARS:
                    # рубим по запятым
                    sub = re.split(r"(?<=,)\s+", sent)
                    cur_sub = ""
                    for s in sub:
                        if len(cur_sub) + len(s) + 1 <= config.SILERO_MAX_CHARS:
                            cur_sub = (cur_sub + " " + s).strip()
                        else:
                            if cur_sub:
                                parts.append(cur_sub)
                            cur_sub = s
                    if cur_sub:
                        current = cur_sub
                    else:
                        current = ""
                else:
                    current = sent
        if current:
            parts.append(current)
        return [p for p in parts if p]

    # ──────────────────────────────────────────────────────────
    # WAV helpers
    # ──────────────────────────────────────────────────────────
    def _to_wav_bytes(self, audio_np: np.ndarray) -> bytes:
        """float32 [-1,1] → WAV bytes (16-bit PCM mono)."""
        audio_clipped = np.clip(audio_np, -1.0, 1.0)
        pcm = (audio_clipped * 32767.0).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    def _concat_wavs(self, wavs: list[bytes]) -> bytes:
        """Склеить несколько WAV (одинаковый формат) в один."""
        if len(wavs) == 1:
            return wavs[0]

        # Извлекаем PCM-фреймы
        pcm_parts: list[bytes] = []
        params: dict[str, int] | None = None
        for w in wavs:
            buf = io.BytesIO(w)
            with wave.open(buf, "rb") as wf:
                if params is None:
                    params = {
                        "channels": wf.getnchannels(),
                        "sampwidth": wf.getsampwidth(),
                        "framerate": wf.getframerate(),
                    }
                pcm_parts.append(wf.readframes(wf.getnframes()))

        if params is None:
            return b""

        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(params["channels"])
            wf.setsampwidth(params["sampwidth"])
            wf.setframerate(params["framerate"])
            wf.writeframes(b"".join(pcm_parts))
        return out.getvalue()

    # ──────────────────────────────────────────────────────────
    # Управление кэшем
    # ──────────────────────────────────────────────────────────
    def warm_cache(self, phrases: list[str]) -> None:
        """Прогреть кэш указанными фразами."""
        for p in phrases:
            try:
                self.synthesize(p)
            except Exception as e:
                logger.warning("TextToSpeech: warm_cache failed for %r: %s", p, e)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()
            self._cache_total_bytes = 0

    @property
    def speaker(self) -> str:
        return self._speaker

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
