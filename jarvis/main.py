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
from jarvis.memory import LongTermMemory, ShortTermMemory


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
                config.GREETING_TEXT,
            ]
        )
    except Exception as e:
        logger.error("Не удалось инициализировать TextToSpeech: %s", e)
        raise

    logger.info("Все компоненты инициализированы")
    return components


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

            # Агентный цикл выполнения действий (ReAct)
            current_input = text
            max_agent_turns = 5
            for turn in range(max_agent_turns):
                try:
                    response_gen = brain.get_response_with_retry(
                        user_text=current_input,
                        long_term_context=long_ctx,
                        max_attempts=3,
                        stream=True,  # Включаем настоящий стриминг
                    )
                except Exception as e:
                    logger.error("Ошибка Brain: %s", e)
                    _speak_async(tts, "Сэр, произошёл сбой. Попробуйте ещё раз.")
                    break

                if isinstance(response_gen, str):
                    # Fallback-ответ (в случае ошибки возвращается строка)
                    full_response = response_gen
                    _speak_async(tts, full_response)
                else:
                    # Настоящий генератор
                    import re
                    # Регулярка для фильтрации тегов "на лету" (упрощенная)
                    tag_pattern = re.compile(r"<[^>]*>")
                    
                    full_response_parts = []
                    buffer = ""
                    in_tag = False
                    
                    for chunk in response_gen:
                        full_response_parts.append(chunk)
                        
                        # Простой парсинг на лету
                        for char in chunk:
                            if char == '<':
                                in_tag = True
                            elif char == '>':
                                in_tag = False
                                continue
                                
                            if not in_tag:
                                buffer += char
                                
                                # Озвучиваем по готовности предложения
                                if buffer and buffer[-1] in ('.', '!', '?') and len(buffer.strip()) > 5:
                                    # Отправляем на озвучку в фоне
                                    _speak_async(tts, buffer.strip())
                                    buffer = ""
                    
                    # Озвучить остаток
                    if buffer.strip():
                        _speak_async(tts, buffer.strip())
                        
                    full_response = "".join(full_response_parts)

                logger.info("Ответ (ход %d): %r", turn + 1, full_response)

                # Выполняем действия, если они есть в тексте
                from jarvis.core.executor import parse_and_execute, ACTION_REGEXPS
                actions = parse_and_execute(full_response)

                if not actions:
                    # Действий больше нет, завершаем цикл
                    break

                # Формируем результаты выполнения для отправки обратно
                observation_parts = []
                for act in actions:
                    observation_parts.append(
                        f"[Результат действия {act['type']} для '{act['param']}']:\n{act['result']}"
                    )
                current_input = "\n\n".join(observation_parts)
                logger.info("Направляю результаты выполнения обратно в Brain: %r", current_input)
                # Короткая пауза перед следующим шагом
                time.sleep(0.5)

            # Факты извлекаются теперь только через теги <save_fact> от ИИ
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