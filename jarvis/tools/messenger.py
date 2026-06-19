"""
tools/messenger.py — Чтение мессенджеров через браузер (Playwright).

Поддерживает WhatsApp Web. Требует однократной авторизации (QR-код),
после чего сессия сохраняется в PLAYWRIGHT_USER_DATA_DIR.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_WHATSAPP_URL = "https://web.whatsapp.com"


def _get_page():
    """Получить браузерную страницу через browser.py синглтон."""
    try:
        from .browser import _get_page as browser_get_page
        return browser_get_page()
    except RuntimeError as e:
        raise RuntimeError(str(e))


def whatsapp_get_messages(chat_name: str, count: int = 5) -> str:
    """
    Прочитать последние сообщения из чата WhatsApp.

    Args:
        chat_name: Имя или часть имени чата/контакта для поиска.
        count: Сколько последних сообщений вернуть (по умолчанию 5).

    Returns:
        Отформатированная строка с сообщениями.
    """
    try:
        page = _get_page()

        # Открываем WhatsApp Web если не там
        if "web.whatsapp.com" not in page.url:
            page.goto(_WHATSAPP_URL, wait_until="networkidle", timeout=60_000)

        # Ждём авторизации — ищем поисковую строку или QR-код
        try:
            page.wait_for_selector('[data-testid="chat-list-search"]', timeout=30_000)
        except Exception:
            # Возможно ожидается QR-код
            qr_present = page.query_selector('canvas[aria-label="Scan me!"]')
            if qr_present:
                return (
                    "WhatsApp требует авторизации через QR-код. "
                    "Пожалуйста, откройте браузер, отсканируйте QR-код и повторите команду."
                )
            return "WhatsApp не загрузился. Проверьте подключение к интернету."

        # Поиск чата
        search_box = page.query_selector('[data-testid="chat-list-search"]')
        if not search_box:
            return "Не удалось найти строку поиска в WhatsApp."

        search_box.click()
        search_box.fill(chat_name)
        time.sleep(1.5)  # Ждём результаты поиска

        # Кликаем на первый результат
        first_result = page.query_selector('[data-testid="cell-frame-container"]')
        if not first_result:
            return f"Чат «{chat_name}» не найден в WhatsApp."

        first_chat_name = first_result.query_selector('[data-testid="cell-frame-title"]')
        actual_name = first_chat_name.inner_text() if first_chat_name else chat_name
        first_result.click()
        time.sleep(1.5)

        # Читаем сообщения
        messages = page.evaluate(f"""
            () => {{
                const msgs = document.querySelectorAll('[data-testid="msg-container"]');
                const result = [];
                const allMsgs = Array.from(msgs).slice(-{count});
                allMsgs.forEach(msg => {{
                    const textEl = msg.querySelector('[data-testid="msg-text"]')
                                || msg.querySelector('.selectable-text');
                    const metaEl = msg.querySelector('[data-testid="msg-meta"]');
                    const fromEl = msg.querySelector('[data-testid="msg-author-glyph"]')
                                || msg.querySelector('span.ggj6brxn');
                    const isOut = msg.querySelector('[data-testid="msg-dblcheck"]') !== null
                               || msg.querySelector('[data-testid="msg-check"]') !== null;
                    if (textEl) {{
                        result.push({{
                            text: textEl.innerText,
                            time: metaEl ? metaEl.innerText : '',
                            from: isOut ? 'Вы' : (fromEl ? fromEl.innerText : 'Контакт'),
                            out: isOut
                        }});
                    }}
                }});
                return result;
            }}
        """)

        if not messages:
            return f"Сообщения в чате «{actual_name}» не найдены или чат пуст."

        lines = [f"Последние {len(messages)} сообщений из «{actual_name}»:", ""]
        for msg in messages:
            direction = "→" if msg.get("out") else "←"
        lines = [f"Последние {len(messages)} сообщений из «{actual_name}»:", ""]
        for msg in messages:
            direction = "→" if msg.get("out") else "←"
            time_str = f" [{msg['time']}]" if msg.get("time") else ""
            lines.append(f"{direction} {msg['from']}{time_str}: {msg['text']}")

        return "\n".join(lines)

    except RuntimeError as e:
        return f"Ошибка: {e}"
    except Exception as e:
        logger.error("messenger.whatsapp_get_messages ошибка: %s", e)
        return f"Ошибка чтения WhatsApp: {e}"


def whatsapp_send_message(chat_name: str, message: str) -> str:
    """
    Отправить сообщение в чат WhatsApp.

    ⚠️ ОПАСНЫЙ — требует голосового подтверждения.

    Args:
        chat_name: Имя чата или контакта.
        message: Текст сообщения для отправки.
    """
    try:
        page = _get_page()

        if "web.whatsapp.com" not in page.url:
            page.goto(_WHATSAPP_URL, wait_until="networkidle", timeout=60_000)

        try:
            page.wait_for_selector('[data-testid="chat-list-search"]', timeout=30_000)
        except Exception:
            return "WhatsApp не загрузился или требует авторизации."

        # Поиск и открытие чата
        search_box = page.query_selector('[data-testid="chat-list-search"]')
        if not search_box:
            return "Не удалось найти строку поиска."

        search_box.click()
        search_box.fill(chat_name)
        time.sleep(1.5)

        first_result = page.query_selector('[data-testid="cell-frame-container"]')
        if not first_result:
            return f"Чат «{chat_name}» не найден."

        first_chat_name = first_result.query_selector('[data-testid="cell-frame-title"]')
        actual_name = first_chat_name.inner_text() if first_chat_name else chat_name
        first_result.click()
        time.sleep(1.0)

        # Вводим и отправляем сообщение
        input_box = page.query_selector('[data-testid="conversation-compose-box-input"]')
        if not input_box:
            return "Не удалось найти поле ввода сообщения."

        input_box.click()
        input_box.fill(message)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(0.5)

        logger.info("messenger: отправлено сообщение в %r", actual_name)
        return f"Сообщение отправлено в «{actual_name}»."

    except RuntimeError as e:
        return f"Ошибка: {e}"
    except Exception as e:
        logger.error("messenger.whatsapp_send_message ошибка: %s", e)
        return f"Ошибка отправки сообщения: {e}"


def telegram_get_messages(chat_name: str, count: int = 5) -> str:
    """
    Прочитать последние сообщения из чата Telegram Web.

    Args:
        chat_name: Имя контакта или чата.
        count: Сколько последних сообщений вернуть.
    """
    try:
        page = _get_page()

        if "web.telegram.org" not in page.url:
            page.goto("https://web.telegram.org/k/", wait_until="networkidle", timeout=60_000)

        # Ждём загрузки приложения
        try:
            page.wait_for_selector(".chatlist-top", timeout=30_000)
        except Exception:
            return (
                "Telegram Web требует авторизации. "
                "Откройте браузер, войдите в аккаунт и повторите команду."
            )

        # Поиск через Ctrl+K
        page.keyboard.press("Control+k")
        time.sleep(0.5)

        search_input = page.query_selector(".search-super-container input")
        if not search_input:
            return "Не удалось открыть поиск в Telegram."

        search_input.fill(chat_name)
        time.sleep(1.5)

        # Клик на первый результат
        first_result = page.query_selector(".search-super-content .chatlist-chat")
        if not first_result:
            return f"Чат «{chat_name}» не найден в Telegram."

        first_result.click()
        time.sleep(1.5)

        # Читаем сообщения
        messages = page.evaluate(f"""
            () => {{
                const msgs = document.querySelectorAll('.message');
                const result = [];
                const allMsgs = Array.from(msgs).slice(-{count});
                allMsgs.forEach(msg => {{
                    const textEl = msg.querySelector('.message-text');
                    const timeEl = msg.querySelector('.time');
                    const nameEl = msg.querySelector('.peer-title');
                    const isOut = msg.classList.contains('is-out');
                    if (textEl) {{
                        result.push({{
                            text: textEl.innerText,
                            time: timeEl ? timeEl.innerText : '',
                            from: isOut ? 'Вы' : (nameEl ? nameEl.innerText : 'Контакт'),
                            out: isOut
                        }});
                    }}
                }});
                return result;
            }}
        """)

        if not messages:
            return f"Сообщения в чате «{chat_name}» не найдены."

        lines = [f"Последние {len(messages)} сообщений из Telegram «{chat_name}»:", ""]
        for msg in messages:
            direction = "→" if msg.get("out") else "←"
            time_str = f" [{msg['time']}]" if msg.get("time") else ""
            lines.append(f"{direction} {msg['from']}{time_str}: {msg['text']}")

        return "\n".join(lines)

    except RuntimeError as e:
        return f"Ошибка: {e}"
    except Exception as e:
        logger.error("messenger.telegram_get_messages ошибка: %s", e)
        return f"Ошибка чтения Telegram: {e}"
