"""
JARVIS — главный оркестратор.
Инициализирует все модули и крутит главный цикл:
  ожидание wake word → запись → STT → Brain → TTS → воспроизведение.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import time
from typing import Any

from jarvis import config
from jarvis.core import (
    Brain,
    SpeechToText,
    TextToSpeech,
    WakeWordListener,
    is_playing,
    play_audio,
    play_beep,
    record_until_silence,
    stop_playback,
)
from jarvis.core.confirm import VoiceConfirm, set_voice_confirm as _set_voice_confirm_global
from jarvis.core import executor as _executor
from jarvis.memory import LongTermMemory, ShortTermMemory
from jarvis.tools import ToolDispatcher


# ──────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────
def _setup_logging() -> None:
    """Файл jarvis.log + консоль, уровень из конфига."""
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)
    # Убираем старые хэндлеры (актуально при перезапуске в IDE)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Консоль
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # Файл (с ротацией)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as e:  # pragma: no cover
        print(f"[WARN] Не удалось открыть файл лога: {e}", file=sys.stderr)

    # Приглушаем шумные сторонние логгеры
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


logger = logging.getLogger("jarvis.main")


# ──────────────────────────────────────────────────────────────
# Обработка управляющих команд
# ──────────────────────────────────────────────────────────────
def _is_exit_command(text: str) -> bool:
    return any(cmd in text.lower() for cmd in config.CMD_EXIT)


def _is_clear_command(text: str) -> bool:
    return any(cmd in text.lower() for cmd in config.CMD_CLEAR_HISTORY)


# ──────────────────────────────────────────────────────────────
# Инициализация компонентов
# ──────────────────────────────────────────────────────────────
def _init_components() -> dict[str, Any]:
    """
    Шаг 1: инициализация всех компонентов.
    Возвращает словарь с готовыми объектами.
    """
    logger.info("=" * 60)
    logger.info("JARVIS — инициализация компонентов")
    logger.info("=" * 60)

    components: dict[str, Any] = {}

    try:
        components["listener"] = WakeWordListener()
    except Exception as e:
        logger.error("Не удалось инициализировать WakeWordListener: %s", e)
        raise

    try:
        components["stt"] = SpeechToText()
    except Exception as e:
        logger.error("Не удалось инициализировать SpeechToText: %s", e)
        raise

    try:
        components["memory_short"] = ShortTermMemory()
        components["memory_long"] = LongTermMemory()
        logger.info(
            "Память: short-term=%d сообщений, long-term=%d фактов",
            config.DIALOG_HISTORY_LIMIT,
            components["memory_long"].count(),
        )
    except Exception as e:
        logger.error("Не удалось инициализировать память: %s", e)
        raise

    try:
        components["brain"] = Brain(short_term=components["memory_short"])
    except Exception as e:
        logger.error("Не удалось инициализировать Brain: %s", e)
        raise

    try:
        components["tts"] = TextToSpeech()
        # Прогреем кэш частыми фразами
        components["tts"].warm_cache(
            [
                "Слушаю, Сэр.",
                "Понял, Сэр.",
                "Не удалось распознать речь, Сэр.",
                "До свидания, Сэр.",
                "Принято, отменяю.",
                "Сэр, не расслышал. Да или нет?",
                "Отменяю для безопасности.",
                config.GREETING_TEXT,
            ]
        )
    except Exception as e:
        logger.error("Не удалось инициализировать TextToSpeech: %s", e)
        raise

    # Голосовое подтверждение
    def _speak_blocking(text: str) -> None:
        """Блокирующая озвучка для VoiceConfirm."""
        try:
            wav = components["tts"].synthesize(text)
            if wav:
                play_audio(wav)
        except Exception as err:
            logger.warning("Ошибка озвучивания подтверждения: %s", err)

    try:
        vc = VoiceConfirm(
            tts=components["tts"],
            stt=components["stt"],
            speak_fn=_speak_blocking,
        )
        components["voice_confirm"] = vc
        # Инъекцируем в executor и глобальный core/confirm
        _executor.set_voice_confirm(vc)
        _set_voice_confirm_global(vc)
        _executor.set_long_term(components["memory_long"])  # Bug B2 fix
        logger.info("VoiceConfirm: инициализирован")
    except Exception as e:
        logger.warning("Не удалось инициализировать VoiceConfirm: %s", e)
        components["voice_confirm"] = None

    # Tool Dispatcher (агентские инструменты)
    try:
        dispatcher = ToolDispatcher()
        components["dispatcher"] = dispatcher
        registered = list(dispatcher.tools.keys())
        logger.info("ToolDispatcher: зарегистрировано %d инструментов: %s", len(registered), registered)
    except Exception as e:
        logger.warning("Не удалось инициализировать ToolDispatcher: %s", e)
        components["dispatcher"] = None

    logger.info("Все компоненты инициализированы")
    return components


# ──────────────────────────────────────────────────────────────
# Гибридный стриминг
# ──────────────────────────────────────────────────────────────
def _stream_and_detect(response_gen: Any, tts: TextToSpeech) -> tuple[str, str]:
    """
    Гибридный обработчик стриминга.
    Определяет тип ответа (json или текст) по первым символам.
    Для текста — воспроизводит потоково через TTS.
    Для JSON — накапливает молча.
    """
    raw_accumulator = ""
    spoken_text = ""
    response_type = "unknown"

    from jarvis.core.executor import ACTION_REGEXPS

    for chunk in response_gen:
        raw_accumulator += chunk

        # Определяем тип ответа по первым символам
        if response_type == "unknown":
            first_char = raw_accumulator.strip()
            if first_char:
                if first_char.startswith("{") or first_char.startswith("```"):
                    response_type = "json"
                else:
                    response_type = "text"

        if response_type == "text":
            # Безопасный стриминг текста (без XML-тегов действий) для TTS
            safe_limit = len(raw_accumulator)
            
            last_lt = raw_accumulator.rfind('<')
            if last_lt != -1 and '>' not in raw_accumulator[last_lt:]:
                safe_limit = last_lt
                
            for tag in ["open_app", "open_url", "run_command", "python_code", "save_fact"]:
                start_pos = 0
                while True:
                    idx = raw_accumulator.find(f"<{tag}", start_pos)
                    if idx == -1: break
                    end_idx = raw_accumulator.find(f"</{tag}>", idx)
                    if end_idx == -1 and idx < safe_limit:
                        safe_limit = idx
                    start_pos = idx + 1
                    
            safe_prefix = raw_accumulator[:safe_limit]
            clean_prefix = safe_prefix
            for regex in ACTION_REGEXPS.values():
                clean_prefix = regex.sub("", clean_prefix)
                
            last_sentence_end = -1
            for char in ('.', '!', '?'):
                idx = clean_prefix.rfind(char)
                if idx > last_sentence_end:
                    last_sentence_end = idx
                    
            if last_sentence_end != -1 and last_sentence_end >= len(spoken_text):
                to_speak = clean_prefix[len(spoken_text):last_sentence_end + 1].strip()
                if to_speak:
                    _speak_async(tts, to_speak)
                spoken_text = clean_prefix[:last_sentence_end + 1]

    # Обработка остатка
    if response_type == "text":
        clean_final = raw_accumulator
        for regex in ACTION_REGEXPS.values():
            clean_final = regex.sub("", clean_final)
            
        to_speak_final = clean_final[len(spoken_text):].strip()
        if to_speak_final:
            _speak_async(tts, to_speak_final)
            
    if response_type == "unknown":
        response_type = "text"

    return raw_accumulator, response_type


# ──────────────────────────────────────────────────────────────
# Главный цикл
# ──────────────────────────────────────────────────────────────
def _main_loop(components: dict[str, Any]) -> None:
    """
    Шаг 3: главный цикл (a-k).
    """
    listener: WakeWordListener = components["listener"]
    stt: SpeechToText = components["stt"]
    brain: Brain = components["brain"]
    tts: TextToSpeech = components["tts"]
    long_term: LongTermMemory = components["memory_long"]

    logger.info("JARVIS готов к работе. Скажите '%s'", config.WAKE_WORD.upper())

    while True:
        try:
            # 3a. ждём wake word
            try:
                # Stop any ongoing playback before listening for wake word
                if is_playing():
                    stop_playback()
                listener.listen()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error("Ошибка при ожидании wake word: %s", e)
                time.sleep(0.5)
                continue

            # 3b. звуковой сигнал активации
            try:
                play_beep()
            except Exception as e:
                logger.warning("Не удалось воспроизвести beep: %s", e)

            # 3c. записываем команду (stop any ongoing playback first)
            if is_playing():
                stop_playback()
            try:
                audio = record_until_silence()
            except Exception as e:
                logger.error("Ошибка записи аудио: %s", e)
                _speak_safe(tts, "Сэр, ошибка записи аудио.")
                continue

            if audio is None or len(audio) == 0:
                logger.debug("Пустая запись — пропускаю итерацию")
                continue

            # 3d. распознаём речь
            text = stt.transcribe(audio)
            if not text:
                logger.info("Речь не распознана — пропускаю")
                continue

            logger.info("Распознано: %r", text)

            # 3e. пустой текст → пропускаем (уже отфильтровано выше)

            # 3f. управляющие команды
            if _is_exit_command(text):
                logger.info("Получена команда выхода")
                _speak_safe(tts, "До свидания, Сэр.")
                break
            if _is_clear_command(text):
                logger.info("Очищаю историю диалога")
                brain.clear_history()
                _speak_safe(tts, "История очищена, Сэр.")
                continue

            # 3g. контекст из долгосрочной памяти
            long_ctx = long_term.to_context_string()

            # Дескриптор инструментов для системного промпта
            tools_prompt = dispatcher.get_tools_prompt() if dispatcher else ""

            # Агентный ReAct-цикл
            current_input = text
            for turn in range(config.AGENT_MAX_TURNS):
                try:
                    response_gen = brain.get_response_with_retry(
                        user_text=current_input,
                        long_term_context=long_ctx,
                        max_attempts=3,
                        stream=True,
                    )
                except Exception as e:
                    logger.error("Ошибка Brain: %s", e)
                    _speak_async(tts, "Сэр, произошёл сбой. Попробуйте ещё раз.")
                    break

                if isinstance(response_gen, str):
                    # Fallback-ответ (ошибка)
                    full_response = response_gen
                    response_type = "text"
                    _speak_async(tts, full_response)
                else:
                    # Гибридный стриминг: JSON или текст
                    full_response, response_type = _stream_and_detect(response_gen, tts)

                logger.info("Ответ (ход %d, тип=%s): %r", turn + 1, response_type, full_response[:200])

                if response_type == "json" and dispatcher:
                    # Агентский tool_call — выполняем инструмент
                    parsed = dispatcher.parse_response(full_response)
                    if parsed.type == "tool_call" and parsed.tool_call:
                        tc = parsed.tool_call
                        logger.info("Тоол-вызов: %r, params=%r", tc.tool, tc.params)
                        result = dispatcher.execute(tc)
                        logger.info("Результат %r: %r", tc.tool, result[:200])
                        current_input = f"[Результат инструмента {tc.tool}]:\n{result}"
                        time.sleep(0.3)
                        continue
                    else:
                        # JSON не распознан — выходим
                        break

                # Обычный текст — ищем XML-теги (fallback)
                from jarvis.core.executor import parse_and_execute
                actions = parse_and_execute(full_response)

                if not actions:
                    break

                # Есть XML-действия — формируем наблюдение
                observation_parts = []
                for act in actions:
                    observation_parts.append(
                        f"[Результат {act['type']} '{act['param']}']:\n{act['result']}"
                    )
                current_input = "\n\n".join(observation_parts)
                logger.info("Направляю результаты XML-действий в Brain: %r", current_input[:200])
                time.sleep(0.5)

            # Факты извлекаются через теги <save_fact> от ИИ
            pass

        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.exception("Неожиданная ошибка в главном цикле: %s", e)
            time.sleep(0.5)
            continue


def _speak_safe(tts: TextToSpeech, text: str) -> None:
    """Безопасный синтез+воспроизведение с логированием ошибок (блокирующий)."""
    try:
        wav = tts.synthesize(text)
        if wav:
            play_audio(wav)
    except Exception as e:
        logger.warning("Ошибка при озвучивании %r: %s", text, e)


def _speak_async(tts: TextToSpeech, text: str) -> None:
    """Запустить _speak_safe в фоновом потоке (non-blocking)."""
    t = threading.Thread(target=_speak_safe, args=(tts, text), daemon=True)
    t.start()


# ──────────────────────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────────────────────
def main() -> int:
    """Шаги 1, 2, 4: setup, приветствие, корректное завершение."""
    _setup_logging()
    logger.info("JARVIS запускается...")

    components: dict[str, Any] | None = None
    try:
        # Шаг 0 — валидация конфигурации (до загрузки тяжёлых моделей)
        config.validate()

        # Шаг 1
        components = _init_components()

        # Шаг 2 — приветствие
        logger.info("Приветствие: %s", config.GREETING_TEXT)
        _speak_safe(components["tts"], config.GREETING_TEXT)

        # Шаг 3 — главный цикл
        _main_loop(components)

    except KeyboardInterrupt:
        logger.info("Получен Ctrl+C — завершаю работу")
    except ValueError as e:
        # Ошибки инициализации (нет API-ключа и т.п.)
        logger.error("Ошибка конфигурации: %s", e)
        return 2
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)
        return 1
    finally:
        # Шаг 4 — корректное завершение
        if components and "listener" in components:
            try:
                components["listener"].close()
            except Exception:  # pragma: no cover
                pass
        if components and "memory_long" in components:
            try:
                components["memory_long"].close()
            except Exception:
                pass
        logger.info("JARVIS завершил работу")

    return 0


if __name__ == "__main__":
    sys.exit(main())