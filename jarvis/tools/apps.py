"""
Инструмент управления приложениями Windows.

Открытие приложений по псевдонимам, URLs в браузере, закрытие процессов.
Мигрирует и расширяет логику из core/executor.py.
"""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Словарь псевдонимов приложений
# ──────────────────────────────────────────────────────────────
# Ключ → значение:
#   "protocol:" → запуск через os.system("start protocol:")
#   "*.exe"     → запуск через subprocess.Popen
#   без расширения → subprocess.Popen (ищет в PATH)

APP_ALIASES: dict[str, str] = {
    # Мессенджеры (URI-протоколы)
    "whatsapp":  "whatsapp:",
    "вотсап":    "whatsapp:",
    "telegram":  "tg:",
    "телеграм":  "tg:",
    "discord":   "discord:",
    "дискорд":   "discord:",

    # Браузеры
    "chrome":    "chrome.exe",
    "хром":      "chrome.exe",
    "firefox":   "firefox.exe",
    "фаерфокс":  "firefox.exe",
    "edge":      "msedge.exe",
    "browser":   "msedge.exe",

    # Системные утилиты
    "notepad":      "notepad.exe",
    "блокнот":      "notepad.exe",
    "explorer":     "explorer.exe",
    "проводник":    "explorer.exe",
    "calc":         "calc.exe",
    "калькулятор":  "calc.exe",
    "taskmgr":      "taskmgr.exe",
    "диспетчер":    "taskmgr.exe",
    "cmd":          "cmd.exe",
    "powershell":   "powershell.exe",
    "paint":        "mspaint.exe",

    # Офис
    "word":         "winword.exe",
    "excel":        "excel.exe",
    "powerpoint":   "powerpnt.exe",
    "outlook":      "outlook.exe",

    # Разработка
    "vscode":    "code",
    "код":       "code",
    "code":      "code",
    "pycharm":   "pycharm64.exe",

    # Медиа
    "spotify":   "spotify.exe",
    "vlc":       "vlc.exe",
    "steam":     "steam.exe",
}


def open_app(name: str) -> str:
    """
    Открыть приложение по имени или псевдониму.

    Args:
        name: Название приложения (псевдоним или путь к .exe).

    Returns:
        Сообщение об успехе или ошибке.
    """
    key = name.strip().lower()
    target = APP_ALIASES.get(key)

    if target is None:
        available = ", ".join(sorted(APP_ALIASES.keys()))
        logger.error("apps.open_app: неизвестное приложение %r", name)
        return (
            f"Не знаю приложение «{name}». "
            f"Доступны: {available[:200]}..."
        )

    logger.info("apps.open_app: %r → %r", name, target)

    try:
        if target.endswith(":"):
            # URI-протокол: whatsapp:, tg:, discord:
            os.startfile(target)
            return f"Приложение запущено: {name}."
        else:
            subprocess.Popen([target], shell=False)
            return f"Приложение запущено: {name}."
    except FileNotFoundError:
        return f"Приложение «{name}» не найдено по пути {target}"
    except Exception as e:
        logger.error("apps.open_app: ошибка: %s", e)
        return f"Ошибка запуска {name!r}: {e}"


def open_url(url: str) -> str:
    """
    Открыть URL в браузере по умолчанию.

    Args:
        url: Адрес страницы (с https:// или без).

    Returns:
        Сообщение об успехе или ошибке.
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    logger.info("apps.open_url: %s", url)
    try:
        webbrowser.open(url)
        return f"Ссылка открыта в браузере: {url}"
    except Exception as e:
        return f"Ошибка открытия ссылки: {e}"


def close_app(name: str) -> str:
    """
    Завершить процесс приложения через taskkill.

    Args:
        name: Имя процесса (например, notepad.exe) или псевдоним.

    Returns:
        Сообщение об успехе или ошибке.
    """
    key = name.strip().lower()
    target = APP_ALIASES.get(key)

    if target is None:
        return f"Не знаю приложение «{name}». Закрытие разрешено только для известных приложений."

    # Извлекаем имя исполняемого файла для taskkill
    if target.endswith(":"):
        target_exe = key + ".exe"
    else:
        target_exe = os.path.basename(target)
        if not target_exe.endswith(".exe"):
            target_exe += ".exe"

    logger.info("apps.close_app: taskkill /IM %s", target_exe)
    try:
        result = subprocess.run(
            ["taskkill", "/IM", target_exe, "/F"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"Приложение {name!r} закрыто."
        else:
            # Попробовать без .exe
            result2 = subprocess.run(
                ["taskkill", "/IM", target, "/F"],
                capture_output=True, text=True, timeout=10
            )
            if result2.returncode == 0:
                return f"Приложение {name!r} закрыто."
            return f"Не удалось закрыть {name!r}: {result.stderr.strip()}"
    except Exception as e:
        return f"Ошибка закрытия {name!r}: {e}"
