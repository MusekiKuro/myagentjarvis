"""
JARVIS Tools — пакет агентских инструментов.

Содержит инструменты для выполнения задач на компьютере пользователя:
поиск в интернете, управление файлами, приложениями, системными настройками,
браузерная автоматизация, мессенджеры, буфер обмена, планировщик задач.

Экспорт:
    ToolDispatcher — основной маршрутизатор tool_call запросов от LLM.
"""

from .dispatcher import ParsedResponse, ToolCall, ToolDispatcher, ToolSpec

__all__ = ["ParsedResponse", "ToolCall", "ToolDispatcher", "ToolSpec"]
