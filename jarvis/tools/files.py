"""
Инструмент работы с файловой системой.

Функции: просмотр директорий, чтение, поиск, запись и удаление файлов.
Опасные операции (запись, удаление) требуют подтверждения через VoiceConfirm.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_path(path: str) -> Path:
    """Раскрыть путь: ~, переменные окружения, относительные."""
    return Path(os.path.expandvars(path)).expanduser().resolve()

_SENSITIVE_PATTERNS = (
    ".env", ".ssh", ".aws", ".kube", ".gnupg",
    "credentials", "id_rsa", "id_ed25519", ".pem", ".key",
    "jarvis_memory.db", "password", "secret", "token",
)

def _is_sensitive_path(resolved_path: Path) -> bool:
    """Проверяет, содержит ли путь критичные для безопасности паттерны."""
    path_str = str(resolved_path).lower()
    return any(pattern in path_str for pattern in _SENSITIVE_PATTERNS)


def list_dir(path: str = ".") -> str:
    """
    Показать содержимое директории.

    Args:
        path: Путь к директории (по умолчанию текущая).

    Returns:
        Форматированная таблица: имя | тип | размер.
    """
    resolved = _resolve_path(path)
    logger.info("files.list_dir: %s", resolved)

    if _is_sensitive_path(resolved):
        # Компромисс: директория чувствительная, поэтому скрываем файлы внутри нее, чтобы не "палить" имена ключей
        return f"Отказано: директория {resolved} содержит чувствительные данные. Просмотр запрещён."

    if not resolved.exists():
        return f"Ошибка: путь не существует: {resolved}"
    if not resolved.is_dir():
        return f"Ошибка: {resolved} — это файл, а не директория."

    try:
        entries = list(resolved.iterdir())
    except PermissionError:
        return f"Ошибка: нет доступа к {resolved}"

    if not entries:
        return f"Директория {resolved} пуста."

    entries.sort(key=lambda e: (e.is_file(), e.name.lower()))

    lines = [f"Содержимое {resolved} ({len(entries)} элементов):"]
    for entry in entries:
        kind = "файл" if entry.is_file() else "папка"
        try:
            size = f"{entry.stat().st_size:,} б" if entry.is_file() else ""
        except OSError:
            size = ""
        lines.append(f"  {entry.name:<40} {kind:<6} {size}")

    return "\n".join(lines)


def read_file(path: str, max_lines: int = 100) -> str:
    """
    Прочитать текстовый файл.

    Args:
        path: Путь к файлу.
        max_lines: Максимум строк для чтения (по умолчанию 100).

    Returns:
        Содержимое файла (первые max_lines строк) или сообщение об ошибке.
    """
    resolved = _resolve_path(path)
    logger.info("files.read_file: %s (max_lines=%d)", resolved, max_lines)

    if _is_sensitive_path(resolved):
        logger.warning("files.read_file: попытка чтения чувствительного пути: %s", resolved)
        return "Отказано: путь указывает на файл с чувствительными данными."

    if not resolved.exists():
        return f"Ошибка: файл не найден: {resolved}"
    if not resolved.is_file():
        return f"Ошибка: {resolved} — директория, не файл."

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"Ошибка: нет доступа к {resolved}"
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

    lines = text.splitlines()
    total = len(lines)
    truncated = lines[:max_lines]
    result = "\n".join(truncated)
    if total > max_lines:
        result += f"\n\n[...показано {max_lines} из {total} строк]"
    return result


def find_file(name: str, search_dir: str = "~") -> str:
    """
    Найти файл по имени или паттерну (рекурсивно).

    Args:
        name: Имя файла или glob-паттерн (например, "*.pdf", "report.docx").
        search_dir: Директория для поиска (по умолчанию домашняя папка).

    Returns:
        Список найденных путей или сообщение об отсутствии.
    """
    resolved = _resolve_path(search_dir)
    logger.info("files.find_file: %r в %s", name, resolved)

    if not resolved.exists():
        return f"Ошибка: директория поиска не существует: {resolved}"

    try:
        raw_found = list(resolved.rglob(name))
        # Фильтруем результаты, чтобы не выдавать расположение секретов
        found = [p for p in raw_found if not _is_sensitive_path(p)]
    except PermissionError:
        return f"Ошибка: нет доступа к {resolved}"
    except Exception as e:
        return f"Ошибка поиска: {e}"

    if not found:
        return f"Файл «{name}» не найден в {resolved}."

    # Ограничим вывод
    MAX_SHOW = 20
    lines = [f"Найдено {len(found)} файл(ов) по паттерну «{name}»:"]
    for p in found[:MAX_SHOW]:
        lines.append(f"  {p}")
    if len(found) > MAX_SHOW:
        lines.append(f"  ... и ещё {len(found) - MAX_SHOW} результатов.")
    return "\n".join(lines)


def write_file(path: str, content: str) -> str:
    """
    Записать текст в файл (создать или перезаписать).

    ⚠️ ОПАСНАЯ операция — требует голосового подтверждения.

    Args:
        path: Путь к файлу.
        content: Содержимое для записи.

    Returns:
        Сообщение об успехе или ошибке.
    """
    resolved = _resolve_path(path)
    logger.info("files.write_file: %s (%d символов)", resolved, len(content))

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Файл записан: {resolved} ({len(content)} символов)."
    except PermissionError:
        return f"Ошибка: нет доступа для записи в {resolved}"
    except Exception as e:
        return f"Ошибка записи файла: {e}"


def delete_file(path: str) -> str:
    """
    Удалить файл.

    ⚠️ ОПАСНАЯ операция — требует голосового подтверждения.

    Args:
        path: Путь к файлу.

    Returns:
        Сообщение об успехе или ошибке.
    """
    resolved = _resolve_path(path)
    logger.info("files.delete_file: %s", resolved)

    if not resolved.exists():
        return f"Ошибка: файл не найден: {resolved}"
    if not resolved.is_file():
        return f"Ошибка: {resolved} — директория. Для удаления папок используйте другой инструмент."

    try:
        resolved.unlink()
        return f"Файл удалён: {resolved}"
    except PermissionError:
        return f"Ошибка: нет доступа для удаления {resolved}"
    except Exception as e:
        return f"Ошибка удаления: {e}"
