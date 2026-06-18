"""
Инструмент управления системными настройками Windows.

Громкость, яркость, батарея, информация о системе.
Требует: pycaw, screen-brightness-control, psutil.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Громкость (pycaw)
# ──────────────────────────────────────────────────────────────

def _get_volume_interface():
    """Вернуть интерфейс управления громкостью Windows (pycaw)."""
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> str:
    """
    Узнать текущий уровень громкости системы.

    Returns:
        Строка вида "Текущая громкость: 45%".
    """
    try:
        vol = _get_volume_interface()
        level = round(vol.GetMasterVolumeLevelScalar() * 100)
        muted = vol.GetMute()
        status = " (отключён звук)" if muted else ""
        return f"Текущая громкость: {level}%{status}."
    except ImportError:
        return "Ошибка: pycaw не установлен. Выполните: pip install pycaw"
    except Exception as e:
        logger.error("system.get_volume: %s", e)
        return f"Ошибка получения громкости: {e}"


def set_volume(level: int | str) -> str:
    """
    Установить уровень громкости системы.

    Args:
        level: Уровень громкости 0-100.

    Returns:
        Подтверждение или сообщение об ошибке.
    """
    try:
        level = int(level)
        level = max(0, min(100, level))
        vol = _get_volume_interface()
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        # Снять mute если был
        if level > 0:
            vol.SetMute(0, None)
        logger.info("system.set_volume: %d%%", level)
        return f"Громкость установлена: {level}%."
    except ImportError:
        return "Ошибка: pycaw не установлен. Выполните: pip install pycaw"
    except Exception as e:
        logger.error("system.set_volume: %s", e)
        return f"Ошибка установки громкости: {e}"


# ──────────────────────────────────────────────────────────────
# Яркость (screen-brightness-control)
# ──────────────────────────────────────────────────────────────

def get_brightness() -> str:
    """
    Узнать текущую яркость экрана.

    Returns:
        Строка вида "Текущая яркость: 70%".
    """
    try:
        import screen_brightness_control as sbc
        brightness = sbc.get_brightness()
        # get_brightness() возвращает list или int
        if isinstance(brightness, list):
            val = brightness[0]
        else:
            val = brightness
        return f"Текущая яркость экрана: {val}%."
    except ImportError:
        return "Ошибка: screen-brightness-control не установлен. Выполните: pip install screen-brightness-control"
    except Exception as e:
        logger.error("system.get_brightness: %s", e)
        return f"Ошибка получения яркости: {e}"


def set_brightness(level: int | str) -> str:
    """
    Установить яркость экрана.

    Args:
        level: Уровень яркости 0-100.

    Returns:
        Подтверждение или сообщение об ошибке.
    """
    try:
        import screen_brightness_control as sbc
        level = int(level)
        level = max(0, min(100, level))
        sbc.set_brightness(level)
        logger.info("system.set_brightness: %d%%", level)
        return f"Яркость экрана установлена: {level}%."
    except ImportError:
        return "Ошибка: screen-brightness-control не установлен."
    except Exception as e:
        logger.error("system.set_brightness: %s", e)
        return f"Ошибка установки яркости: {e}"


# ──────────────────────────────────────────────────────────────
# Батарея и системная информация (psutil)
# ──────────────────────────────────────────────────────────────

def get_battery() -> str:
    """
    Узнать заряд батареи и статус зарядки.

    Returns:
        Строка вида "Батарея: 75%, заряжается." или "Питание от сети."
    """
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return "Батарея не обнаружена (стационарный ПК или батарея не определена)."
        percent = round(battery.percent)
        if battery.power_plugged:
            status = "заряжается" if battery.percent < 100 else "заряжена полностью"
        else:
            secs = battery.secsleft
            if secs and secs > 0:
                hours, mins = divmod(secs // 60, 60)
                time_str = f", осталось ~{hours}ч {mins}м" if hours else f", осталось ~{mins}м"
            else:
                time_str = ""
            status = f"от батареи{time_str}"
        return f"Батарея: {percent}%, {status}."
    except ImportError:
        return "Ошибка: psutil не установлен. Выполните: pip install psutil"
    except Exception as e:
        logger.error("system.get_battery: %s", e)
        return f"Ошибка получения информации о батарее: {e}"


def get_system_info() -> str:
    """
    Получить информацию о системе: загрузка CPU, RAM, диск.

    Returns:
        Многострочная строка со статистикой.
    """
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)

        lines = [
            "Информация о системе:",
            f"  CPU: {cpu:.1f}%",
            f"  RAM: {ram_used_gb:.1f} / {ram_total_gb:.1f} ГБ ({ram.percent:.0f}%)",
            f"  Диск C:\\: {disk_used_gb:.1f} / {disk_total_gb:.1f} ГБ ({disk.percent:.0f}%)",
        ]
        return "\n".join(lines)
    except ImportError:
        return "Ошибка: psutil не установлен. Выполните: pip install psutil"
    except Exception as e:
        logger.error("system.get_system_info: %s", e)
        return f"Ошибка получения информации о системе: {e}"
