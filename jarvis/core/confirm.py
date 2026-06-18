"""
Голосовое подтверждение опасных действий.

JARVIS озвучивает вопрос, записывает ответ пользователя через микрофон,
распознаёт его через Whisper и возвращает True (разрешено) или False (отклонено).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from .. import config

if TYPE_CHECKING:
    from .stt import SpeechToText
    from .tts import TextToSpeech

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Словари ответов
# ──────────────────────────────────────────────────────────────
_CONFIRM_WORDS: frozenset[str] = frozenset({
    "да", "разрешаю", "давай", "ок", "окей", "подтверждаю",
    "конечно", "можно", "валяй", "yes", "yep", "разрешить",
    "выполняй", "делай", "принято", "согласен",
})

_DENY_WORDS: frozenset[str] = frozenset({
    "нет", "отмена", "стоп", "не надо", "отставить", "no",
    "cancel", "отменить", "запрети", "запрещаю", "откажи",
    "откажись", "не делай", "не выполняй",
})


class VoiceConfirm:
    """
    Голосовое подтверждение опасных действий.

    Использует существующие экземпляры TTS и STT — новые модели не загружаются.
    """

    def __init__(
        self,
        tts: "TextToSpeech",
        stt: "SpeechToText",
        speak_fn: Callable[[str], None],
    ) -> None:
        """
        Args:
            tts: Экземпляр TextToSpeech (Silero). Используется для синтеза.
            stt: Экземпляр SpeechToText (Whisper). Используется для распознавания.
            speak_fn: Блокирующая функция озвучивания: speak_fn(text) воспроизводит WAV синхронно.
        """
        self._tts = tts
        self._stt = stt
        self._speak = speak_fn

    def ask(self, question: str) -> bool:
        """
        Озвучить вопрос, записать ответ пользователя и вернуть решение.

        Args:
            question: Вопрос для озвучивания, например:
                      "Сэр, хочу удалить файл report.docx. Разрешаете?"

        Returns:
            True если пользователь разрешил, False если запретил или промолчал.

        Алгоритм:
            1. Озвучить вопрос через TTS.
            2. Записать ответ (VAD, макс. VOICE_CONFIRM_MAX_SECONDS сек).
            3. Распознать через Whisper.
            4. Если совпадение с _CONFIRM_WORDS → True.
            5. Если совпадение с _DENY_WORDS или тишина → False + "Отменяю".
            6. Если ни то, ни другое → переспросить один раз → False если снова непонятно.
        """
        from .listener import record_until_silence

        # 1. Озвучить вопрос
        logger.info("VoiceConfirm.ask: %r", question)
        self._speak(question)

        # 2. Первая попытка
        result = self._listen_and_parse()
        if result is True:
            return True
        if result is False:
            self._speak("Принято, отменяю.")
            return False

        # result is None — не распознано, переспросить один раз
        self._speak("Сэр, не расслышал. Да или нет?")
        result2 = self._listen_and_parse()
        if result2 is True:
            return True

        # Тишина или непонятный ответ повторно — безопасный дефолт: отказ
        self._speak("Отменяю для безопасности.")
        logger.info("VoiceConfirm: не получили чёткого ответа — отказ.")
        return False

    def _listen_and_parse(self) -> bool | None:
        """
        Записать аудио и распознать ответ.

        Returns:
            True  — чёткое согласие
            False — чёткий отказ или тишина
            None  — ответ не распознан (нет совпадений)
        """
        from .listener import record_until_silence

        audio = record_until_silence(max_seconds=config.VOICE_CONFIRM_MAX_SECONDS)

        if audio is None or len(audio) == 0:
            logger.info("VoiceConfirm: тишина — считаем отказом.")
            return False

        text = self._stt.transcribe(audio).lower().strip()
        logger.info("VoiceConfirm: распознано %r", text)

        if not text:
            return False

        words = set(text.split())
        # Проверяем вхождение любого слова из словарей
        if words & _CONFIRM_WORDS:
            logger.info("VoiceConfirm: подтверждение.")
            return True
        if words & _DENY_WORDS:
            logger.info("VoiceConfirm: отказ.")
            return False

        # Фраза произнесена, но не распознана как да/нет
        logger.info("VoiceConfirm: ответ не распознан (%r).", text)
        return None


# ──────────────────────────────────────────────────────────────
# Глобальный экземпляр (устанавливается из main.py)
# ──────────────────────────────────────────────────────────────
_voice_confirm_instance: VoiceConfirm | None = None


def set_voice_confirm(vc: VoiceConfirm) -> None:
    """Зарегистрировать глобальный экземпляр VoiceConfirm из main.py."""
    global _voice_confirm_instance
    _voice_confirm_instance = vc
    logger.info("VoiceConfirm: глобальный экземпляр установлен.")


def get_voice_confirm() -> VoiceConfirm | None:
    """Получить глобальный экземпляр VoiceConfirm (может быть None до инициализации)."""
    return _voice_confirm_instance
