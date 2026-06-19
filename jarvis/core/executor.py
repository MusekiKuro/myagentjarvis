"""
Модуль выполнения действий (XML-теги) JARVIS.
Принимает распарсенные теги от LLM и выполняет их локально на ПК.
Для быстрых действий (запуск приложений, ссылок, сохранение фактов).
Опасные операции (run_command, python_code) — голосовое подтверждение.
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import sys
import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory.long_term import LongTermMemory
    from .confirm import VoiceConfirm

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Глобальные зависимости (инициализируются из main.py)
# ──────────────────────────────────────────────────────────────
_voice_confirm: VoiceConfirm | None = None
_long_term: LongTermMemory | None = None  # Bug B2 fix: используем существующий экземпляр


def set_voice_confirm(vc: VoiceConfirm) -> None:
    """[Маин] Установить глобальный экземпляр голосового подтверждения."""
    global _voice_confirm
    _voice_confirm = vc
    logger.info("Executor: VoiceConfirm установлен.")


def set_long_term(ltm: LongTermMemory) -> None:
    """[Маин] Передать экземпляр LongTermMemory (Bug B2 fix)."""
    global _long_term
    _long_term = ltm
    logger.info("Executor: LongTermMemory установлен.")

# Регулярные выражения для поиска тегов действий
ACTION_REGEXPS = {
    "open_app": re.compile(r"<open_app>(.*?)</open_app>", re.DOTALL),
    "open_url": re.compile(r"<open_url>(.*?)</open_url>", re.DOTALL),
    "run_command": re.compile(r"<run_command>(.*?)</run_command>", re.DOTALL),
    "python_code": re.compile(r"<python_code>(.*?)</python_code>", re.DOTALL),
    "save_fact": re.compile(r'<save_fact\s+category="([^"]+)"\s+key="([^"]+)">([^<]+)</save_fact>', re.DOTALL),
}


def open_app(app_name: str) -> str:
    """Запустить приложение на Windows по имени или протоколу. Делегирует в tools/apps."""
    from ..tools.apps import open_app as _open_app
    return _open_app(app_name)


def open_url(url: str) -> str:
    """Открыть URL-ссылку в браузере по умолчанию. Делегирует в tools/apps."""
    from ..tools.apps import open_url as _open_url
    return _open_url(url)


def run_command(cmd: str) -> str:
    """Выполнить системную команду терминала (CMD/PowerShell) и вернуть вывод."""
    cmd = cmd.strip()
    logger.info("Executor: Запрос на выполнение команды %r", cmd)

    from jarvis import config
    if config.REQUIRE_ACTION_CONFIRMATION:
        if _voice_confirm is None:
            logger.error("Executor: VoiceConfirm не инициализирован, опасная команда отменена.")
            return "Действие отменено: голосовое подтверждение недоступно."
            
        if not _voice_confirm.ask(f"Сэр, хочу выполнить команду терминала: {cmd}. Разрешаете?"):
            logger.info("Executor: Команда отклонена пользователем.")
            return "Действие отменено пользователем."

    logger.info("Executor: Выполнение команды %r", cmd)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=15,
        )

        # Функция декодирования с автоопределением кодировки (Windows часто отдает CP866)
        def decode_bytes(b: bytes) -> str:
            for enc in ["utf-8", "cp866", "cp1251"]:
                try:
                    return b.decode(enc)
                except UnicodeDecodeError:
                    continue
            return b.decode("utf-8", errors="ignore")

        stdout = decode_bytes(result.stdout).strip()
        stderr = decode_bytes(result.stderr).strip()

        if not stdout and not stderr:
            return f"Команда '{cmd}' успешно выполнена без вывода."

        output = []
        if stdout:
            output.append(f"Вывод команды:\n{stdout}")
        if stderr:
            output.append(f"Ошибки/Предупреждения:\n{stderr}")

        return "\n\n".join(output)

    except subprocess.TimeoutExpired:
        logger.warning("Executor: Превышен тайм-аут выполнения команды %r", cmd)
        return "Ошибка: превышен тайм-аут выполнения команды (15 сек)."
    except Exception as e:
        logger.error("Executor: Ошибка выполнения команды %r: %s", cmd, e)
        return f"Ошибка выполнения команды: {e}"


def run_python(code: str) -> str:
    """Запустить произвольный Python-код и вернуть результат (stdout/stderr/variables)."""
    code = code.strip()
    logger.info("Executor: Запрос на запуск Python-кода (длина: %d симв.)", len(code))

    from jarvis import config
    if config.REQUIRE_ACTION_CONFIRMATION:
        if _voice_confirm is None:
            logger.error("Executor: VoiceConfirm не инициализирован, опасный python-код отменен.")
            return "Действие отменено: голосовое подтверждение недоступно."
            
        if not _voice_confirm.ask("Сэр, хочу запустить Python-код. Разрешаете?"):
            logger.info("Executor: Python-код отклонён пользователем.")
            return "Действие отменено пользователем."

    logger.info("Executor: Запуск Python-кода")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    sys.stdout = stdout_buf
    sys.stderr = stderr_buf

    global_env: dict[str, Any] = {}
    local_env: dict[str, Any] = {}

    try:
        # Выполняем код
        exec(code, global_env, local_env)

        sys.stdout = old_stdout
        sys.stderr = old_stderr

        stdout = stdout_buf.getvalue().strip()
        stderr = stderr_buf.getvalue().strip()

        if not stdout and not stderr:
            # Если вывода не было, попробуем вернуть значимые локальные переменные
            user_vars = {k: v for k, v in local_env.items() if not k.startswith("_")}
            if user_vars:
                return f"Код выполнен. Локальные переменные: {user_vars}"
            return "Код выполнен успешно без вывода."

        output = []
        if stdout:
            output.append(stdout)
        if stderr:
            output.append(f"Ошибки:\n{stderr}")

        return "\n".join(output)

    except Exception as e:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        tb = traceback.format_exc()
        logger.error("Executor: Ошибка выполнения Python-кода: %s", e)
        return f"Ошибка выполнения Python-кода: {e}\n{tb}"


def parse_and_execute(text: str) -> list[dict[str, str]]:
    """
    Сканирует текст на наличие XML-тегов действий и последовательно выполняет их.
    Возвращает список результатов выполнения в формате:
    [{'type': 'open_app', 'param': 'notepad', 'result': '...'}]
    """
    results: list[dict[str, str]] = []

    # Ищем вхождения тегов. Так как порядок выполнения важен,
    # мы находим все теги и выполняем их по очереди появления.
    matches: list[tuple[int, str, Any]] = []  # (index, action_type, content)

    for action_type, regex in ACTION_REGEXPS.items():
        for match in regex.finditer(text):
            if action_type == "save_fact":
                matches.append((match.start(), action_type, match.groups()))
            else:
                matches.append((match.start(), action_type, match.group(1).strip()))

    # Сортируем по индексу появления в тексте
    matches.sort(key=lambda x: x[0])

    for _, action_type, content in matches:
        result_str = ""
        if action_type == "open_app":
            result_str = open_app(content)
        elif action_type == "open_url":
            result_str = open_url(content)
        elif action_type == "run_command":
            result_str = run_command(content)
        elif action_type == "python_code":
            result_str = run_python(content)
        elif action_type == "save_fact":
            category, key, value = content
            category = category.strip()
            key = key.strip()
            value = value.strip()
            try:
                # Bug B2 fix: используем инъекцированный экземпляр, если есть
                if _long_term is not None:
                    _long_term.save_fact(category, key, value)
                else:
                    from jarvis.memory.long_term import LongTermMemory
                    with LongTermMemory() as ltm:
                        ltm.save_fact(category, key, value)
                result_str = f"Факт сохранён: [{category}] {key} = {value}"
            except Exception as e:
                logger.error("Executor: Ошибка сохранения факта: %s", e)
                result_str = f"Ошибка сохранения факта: {e}"

        results.append({
            "type": action_type,
            "param": str(content),
            "result": result_str,
        })

    return results
