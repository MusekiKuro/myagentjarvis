"""
tools/gui.py — Управление графическим интерфейсом (мышь, клавиатура).

Использует pyautogui для автоматизации действий пользователя.
⚠️ ВСЕ действия здесь потенциально опасны, но для удобства 
мы сделаем опасными только клики и ввод текста.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_mouse_position() -> str:
    """Получить текущие координаты мыши."""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return f"Координаты мыши: x={x}, y={y}"
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"


def move_mouse(x: int, y: int, duration: float = 0.5) -> str:
    """
    Переместить мышь в указанные координаты.
    """
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=duration)
        return f"Мышь перемещена на координаты ({x}, {y})."
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"


def click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> str:
    """
    Кликнуть мышью.

    ⚠️ Требует подтверждения.
    """
    try:
        import pyautogui
        if x is not None and y is not None:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            coord_str = f" на ({x}, {y})"
        else:
            pyautogui.click(button=button, clicks=clicks)
            coord_str = " на текущей позиции"

        return f"Выполнен клик ({button}, {clicks} раз){coord_str}."
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"


def type_text(text: str, interval: float = 0.05) -> str:
    """
    Ввести текст с клавиатуры.

    ⚠️ Требует подтверждения.
    """
    try:
        import pyautogui
        pyautogui.write(text, interval=interval)
        return f"Введён текст: {text[:50]}..."
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"


def press_key(key: str) -> str:
    """
    Нажать клавишу (например, 'enter', 'esc', 'win', 'ctrl', 'c').

    ⚠️ Требует подтверждения.
    """
    try:
        import pyautogui
        pyautogui.press(key)
        return f"Нажата клавиша: {key}"
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"


def hotkey(*keys: str) -> str:
    """
    Выполнить сочетание клавиш (например, 'ctrl', 'c').

    ⚠️ Требует подтверждения.
    """
    try:
        import pyautogui
        pyautogui.hotkey(*keys)
        return f"Выполнено сочетание клавиш: {' + '.join(keys)}"
    except ImportError:
        return "Ошибка: pyautogui не установлен."
    except Exception as e:
        return f"Ошибка: {e}"
