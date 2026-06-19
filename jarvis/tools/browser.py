"""
tools/browser.py — Браузерная автоматизация через Playwright.
Позволяет JARVIS открывать страницы, читать текст, кликать, заполнять формы.

Требует:
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from jarvis import config

logger = logging.getLogger(__name__)

# Глобальный синглтон браузера/страницы для переиспользования
_playwright = None
_browser = None
_page = None


def _get_page():
    """Получить (или создать) persistent Playwright page."""
    global _playwright, _browser, _page

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright не установлен. Выполните: pip install playwright && playwright install chromium"
        )

    if _playwright is None:
        _playwright = sync_playwright().start()

    if _browser is None or not _browser.is_connected():
        user_data_dir = str(getattr(config, "PLAYWRIGHT_USER_DATA_DIR",
                                   Path.home() / ".jarvis_browser_profile"))
        os.makedirs(user_data_dir, exist_ok=True)

        _browser = _playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # False — браузер видим (нужен для входа WhatsApp и т.п.)
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    if not _browser.pages:
        _page = _browser.new_page()
    else:
        _page = _browser.pages[-1]

    return _page


def _cleanup_text(raw: str) -> str:
    """Удалить лишние пробелы и повторяющиеся переводы строк."""
    text = re.sub(r"\n{3,}", "\n\n", raw)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def open_page(url: str) -> str:
    """
    Открыть страницу по URL.

    Args:
        url: URL для открытия. http/https добавляется автоматически.
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        page = _get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        title = page.title()
        logger.info("Browser: открыта страница %r (title=%r)", url, title)
        return f"Страница открыта: {title}\nURL: {url}"
    except Exception as e:
        logger.error("Browser.open_page ошибка: %s", e)
        return f"Ошибка открытия страницы: {e}"


def get_page_text(max_chars: int = 3000) -> str:
    """
    Получить текстовое содержимое текущей страницы.

    Args:
        max_chars: Максимальное количество символов для возврата.
    """
    try:
        page = _get_page()
        # Берём текст из body — убираем скрипты/стили
        text = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script, style, nav, footer, header, aside');
                scripts.forEach(s => s.remove());
                return document.body ? document.body.innerText : '';
            }
        """)
        clean = _cleanup_text(str(text))
        if len(clean) > max_chars:
            clean = clean[:max_chars] + f"\n\n… (обрезано, всего {len(clean)} символов)"
        return clean or "Страница пуста или не загружена."
    except Exception as e:
        logger.error("Browser.get_page_text ошибка: %s", e)
        return f"Ошибка получения текста страницы: {e}"


def click_element(selector: str) -> str:
    """
    Кликнуть на элемент по CSS-селектору.

    Args:
        selector: CSS-селектор элемента (например, 'button[type=submit]').
    """
    try:
        page = _get_page()
        page.click(selector, timeout=10_000)
        logger.info("Browser: клик по %r", selector)
        return f"Клик по элементу «{selector}» выполнен."
    except Exception as e:
        logger.error("Browser.click_element ошибка: %s", e)
        return f"Ошибка клика по «{selector}»: {e}"


def fill_form(selector: str, text: str) -> str:
    """
    Заполнить поле ввода текстом.

    Args:
        selector: CSS-селектор поля ввода.
        text: Текст для ввода.
    """
    try:
        page = _get_page()
        page.fill(selector, text, timeout=10_000)
        logger.info("Browser: заполнено поле %r значением %r", selector, text[:50])
        return f"Поле «{selector}» заполнено."
    except Exception as e:
        logger.error("Browser.fill_form ошибка: %s", e)
        return f"Ошибка заполнения поля «{selector}»: {e}"


def screenshot(save_path: str | None = None) -> str:
    """
    Сделать скриншот текущей страницы.

    Args:
        save_path: Путь для сохранения (PNG). По умолчанию — рабочий стол.
    """
    try:
        if save_path is None:
            desktop = Path.home() / "Desktop"
            desktop.mkdir(exist_ok=True)
            save_path = str(desktop / "jarvis_screenshot.png")

        page = _get_page()
        page.screenshot(path=save_path, full_page=False)
        logger.info("Browser: скриншот сохранён в %r", save_path)
        return f"Скриншот сохранён: {save_path}"
    except Exception as e:
        logger.error("Browser.screenshot ошибка: %s", e)
        return f"Ошибка скриншота: {e}"


def search_web_browser(query: str) -> str:
    """
    Поиск через браузер (DuckDuckGo).

    Args:
        query: Поисковый запрос.
    """
    try:
        import urllib.parse
        encoded = urllib.parse.quote_plus(query)
        url = f"https://duckduckgo.com/?q={encoded}&ia=web"
        page = _get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # Ждём результаты
        page.wait_for_selector("[data-result]", timeout=10_000)
        results = page.evaluate("""
            () => {
                const items = document.querySelectorAll('[data-result]');
                const results = [];
                items.forEach((item, i) => {
                    if (i >= 5) return;
                    const title = item.querySelector('h2');
                    const snippet = item.querySelector('[data-result="snippet"]');
                    const link = item.querySelector('a[href]');
                    if (title && link) {
                        results.push({
                            title: title.innerText,
                            snippet: snippet ? snippet.innerText : '',
                            url: link.href
                        });
                    }
                });
                return results;
            }
        """)
        if not results:
            return "Результаты поиска не найдены."
        lines = [f"Поиск: «{query}»", ""]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r['snippet']:
                lines.append(f"   {r['snippet']}")
            lines.append(f"   {r['url']}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("Browser.search_web_browser ошибка: %s", e)
        return f"Ошибка браузерного поиска: {e}"


def get_current_url() -> str:
    """Получить текущий URL браузера."""
    try:
        page = _get_page()
        return f"Текущий URL: {page.url}"
    except Exception as e:
        return f"Ошибка: {e}"


def close_browser() -> str:
    """Закрыть браузер и освободить ресурсы."""
    global _playwright, _browser, _page
    try:
        if _browser:
            _browser.close()
            _browser = None
            _page = None
        if _playwright:
            _playwright.stop()
            _playwright = None
        return "Браузер закрыт."
    except Exception as e:
        logger.error("Browser.close ошибка: %s", e)
        return f"Ошибка закрытия браузера: {e}"
