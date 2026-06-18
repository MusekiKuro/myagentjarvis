"""
Поисковый инструмент — DuckDuckGo.

Выполняет веб-поиск без API-ключей через библиотеку duckduckgo-search.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 5) -> str:
    """
    Поиск в интернете через DuckDuckGo.

    Требует: pip install duckduckgo-search

    Args:
        query: Поисковый запрос.
        max_results: Максимальное количество результатов (1-10).

    Returns:
        Форматированная строка с результатами:
            1. [Заголовок] — краткое описание
               URL: https://...
            2. ...
        Или сообщение об ошибке.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.error("web_search: duckduckgo-search не установлен.")
        return "Ошибка: библиотека duckduckgo-search не установлена. Выполните: pip install duckduckgo-search"

    max_results = max(1, min(int(max_results), 10))
    logger.info("web_search: запрос %r, max_results=%d", query, max_results)

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        logger.error("web_search: ошибка поиска: %s", e)
        return f"Ошибка поиска: {e}"

    if not results:
        return f"По запросу «{query}» ничего не найдено."

    lines = [f"Результаты поиска по запросу «{query}»:"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "—")
        body = r.get("body", "—")
        url = r.get("href", "—")
        # Обрезать длинные описания
        if len(body) > 200:
            body = body[:197] + "..."
        lines.append(f"\n{i}. [{title}]\n   {body}\n   URL: {url}")

    return "\n".join(lines)
