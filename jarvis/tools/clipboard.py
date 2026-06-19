"""
tools/clipboard.py — Работа с буфером обмена.
Использует pyperclip для кроссплатформенного доступа к clipboard.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_clipboard() -> str:
    """Получить текущее содержимое буфера обмена."""
    try:
        import pyperclip
        text = pyperclip.paste()
        if not text:
            return "Буфер обмена пуст."
        return f"Содержимое буфера обмена:\n{text}"
    except ImportError:
        return "Ошибка: pyperclip не установлен (pip install pyperclip)."
    except Exception as e:
        logger.error("Ошибка чтения буфера обмена: %s", e)
        return f"Ошибка чтения буфера обмена: {e}"


def set_clipboard(text: str) -> str:
    """Записать текст в буфер обмена."""
    try:
        import pyperclip
        pyperclip.copy(text)
        preview = text[:80] + ("…" if len(text) > 80 else "")
        logger.info("Clipboard: записан текст %r", preview)
        return f"Скопировано в буфер обмена: «{preview}»"
    except ImportError:
        return "Ошибка: pyperclip не установлен (pip install pyperclip)."
    except Exception as e:
        logger.error("Ошибка записи в буфер обмена: %s", e)
        return f"Ошибка записи в буфер обмена: {e}"


def clear_clipboard() -> str:
    """Очистить буфер обмена."""
    try:
        import pyperclip
        pyperclip.copy("")
        return "Буфер обмена очищен."
    except ImportError:
        return "Ошибка: pyperclip не установлен."
    except Exception as e:
        logger.error("Ошибка очистки буфера обмена: %s", e)
        return f"Ошибка очистки буфера обмена: {e}"
