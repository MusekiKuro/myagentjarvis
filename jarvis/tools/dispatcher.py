"""
Tool Dispatcher — маршрутизатор вызовов инструментов (tool_call) от LLM.

Принимает строку ответа LLM, определяет тип (JSON tool_call или обычный текст),
маршрутизирует вызов к нужному инструменту и возвращает результат.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Типы данных
# ──────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """Распознанный вызов инструмента из ответа LLM."""
    tool: str                    # Имя инструмента: "search", "files.list_dir", etc.
    params: dict[str, Any]       # Параметры вызова


@dataclass
class ParsedResponse:
    """Результат разбора ответа LLM."""
    type: str                    # "text" | "tool_call"
    text: str = ""               # Исходный текст ответа LLM
    tool_call: ToolCall | None = None  # Заполнен только при type="tool_call"


@dataclass
class ToolSpec:
    """Спецификация зарегистрированного инструмента."""
    name: str                    # Уникальное имя: "search"
    description: str             # Описание для системного промпта LLM
    parameters: dict[str, str]   # {"query": "строка поискового запроса (обязательный)"}
    handler: Callable[..., str]  # Функция-обработчик
    dangerous: bool = False      # Требует ли голосового подтверждения


# Регулярка для извлечения JSON из markdown-блоков (```json ... ```)
_JSON_MD_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ToolDispatcher:
    """
    Маршрутизатор вызовов инструментов.

    Использование:
        dispatcher = ToolDispatcher()
        parsed = dispatcher.parse_response(llm_response)
        if parsed.type == "tool_call":
            result = dispatcher.execute(parsed.tool_call)
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._register_builtin_tools()

    # ──────────────────────────────────────────────────────────
    # Регистрация инструментов
    # ──────────────────────────────────────────────────────────

    def register(self, spec: ToolSpec) -> None:
        """Зарегистрировать инструмент в диспетчере."""
        self._tools[spec.name] = spec
        logger.debug("ToolDispatcher: зарегистрирован инструмент %r", spec.name)

    def _register_builtin_tools(self) -> None:
        """Зарегистрировать все встроенные инструменты."""

        # --- Поиск ---
        try:
            from .search import web_search
            self.register(ToolSpec(
                name="search",
                description="Поиск информации в интернете через DuckDuckGo.",
                parameters={
                    "query": "строка поискового запроса (обязательный)",
                    "max_results": "количество результатов, по умолчанию 5 (необязательный)",
                },
                handler=web_search,
                dangerous=False,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: search недоступен (duckduckgo-search не установлен).")

        # --- Файлы ---
        try:
            from . import files as files_mod
            self.register(ToolSpec(
                name="files.list_dir",
                description="Показать содержимое папки.",
                parameters={"path": "путь к папке (необязательный, по умолчанию текущая)"},
                handler=files_mod.list_dir,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="files.read_file",
                description="Прочитать текстовый файл.",
                parameters={
                    "path": "путь к файлу (обязательный)",
                    "max_lines": "максимум строк, по умолчанию 100 (необязательный)",
                },
                handler=files_mod.read_file,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="files.find_file",
                description="Найти файл по имени или паттерну.",
                parameters={
                    "name": "имя файла или паттерн (обязательный)",
                    "search_dir": "где искать, по умолчанию домашняя папка (необязательный)",
                },
                handler=files_mod.find_file,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="files.write_file",
                description="Записать текст в файл. Требует голосового подтверждения.",
                parameters={
                    "path": "путь к файлу (обязательный)",
                    "content": "содержимое файла (обязательный)",
                },
                handler=files_mod.write_file,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="files.delete_file",
                description="Удалить файл. Требует голосового подтверждения.",
                parameters={"path": "путь к файлу (обязательный)"},
                handler=files_mod.delete_file,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: files недоступен.")

        # --- Приложения ---
        try:
            from . import apps as apps_mod
            self.register(ToolSpec(
                name="apps.open_app",
                description="Открыть приложение или программу.",
                parameters={"name": "название или псевдоним приложения (обязательный)"},
                handler=apps_mod.open_app,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="apps.open_url",
                description="Открыть ссылку в браузере.",
                parameters={"url": "URL-адрес (обязательный)"},
                handler=apps_mod.open_url,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="apps.close_app",
                description="Закрыть запущенное приложение.",
                parameters={"name": "имя процесса или приложения (обязательный)"},
                handler=apps_mod.close_app,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: apps недоступен.")

        # --- Система ---
        try:
            from . import system as sys_mod
            self.register(ToolSpec(
                name="system.set_volume",
                description="Установить громкость системы (0-100).",
                parameters={"level": "уровень громкости 0-100 (обязательный)"},
                handler=sys_mod.set_volume,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="system.get_volume",
                description="Узнать текущий уровень громкости.",
                parameters={},
                handler=sys_mod.get_volume,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="system.set_brightness",
                description="Установить яркость экрана (0-100).",
                parameters={"level": "уровень яркости 0-100 (обязательный)"},
                handler=sys_mod.set_brightness,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="system.get_brightness",
                description="Узнать текущую яркость экрана.",
                parameters={},
                handler=sys_mod.get_brightness,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="system.get_battery",
                description="Узнать заряд батареи и статус зарядки.",
                parameters={},
                handler=sys_mod.get_battery,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="system.get_info",
                description="Получить информацию о системе: CPU, RAM, диск.",
                parameters={},
                handler=sys_mod.get_system_info,
                dangerous=False,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: system недоступен (pycaw/psutil не установлены).")

        # --- Буфер обмена ---
        try:
            from . import clipboard as clip_mod
            self.register(ToolSpec(
                name="clipboard.get",
                description="Прочитать текущее содержимое буфера обмена.",
                parameters={},
                handler=clip_mod.get_clipboard,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="clipboard.set",
                description="Записать текст в буфер обмена.",
                parameters={"text": "текст для записи в буфер обмена (обязательный)"},
                handler=clip_mod.set_clipboard,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: clipboard недоступен (pyperclip не установлен).")

        # --- Браузер (Playwright) ---
        try:
            from . import browser as browser_mod
            self.register(ToolSpec(
                name="browser.open",
                description="Открыть страницу в браузере по URL.",
                parameters={"url": "адрес страницы (обязательный)"},
                handler=browser_mod.open_page,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="browser.get_text",
                description="Получить текстовое содержимое текущей страницы браузера.",
                parameters={"max_chars": "максимум символов, по умолчанию 3000 (необязательный)"},
                handler=browser_mod.get_page_text,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="browser.click",
                description="Кликнуть на элемент страницы по CSS-селектору.",
                parameters={"selector": "CSS-селектор элемента (обязательный)"},
                handler=browser_mod.click_element,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="browser.fill",
                description="Заполнить поле ввода на странице.",
                parameters={
                    "selector": "CSS-селектор поля (обязательный)",
                    "text": "текст для ввода (обязательный)",
                },
                handler=browser_mod.fill_form,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="browser.screenshot",
                description="Сделать скриншот текущей страницы браузера.",
                parameters={"save_path": "путь для сохранения PNG (необязательный)"},
                handler=browser_mod.screenshot,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="browser.search",
                description="Поиск в интернете через браузер (DuckDuckGo).",
                parameters={"query": "поисковый запрос (обязательный)"},
                handler=browser_mod.search_web_browser,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="browser.url",
                description="Получить текущий URL открытой страницы браузера.",
                parameters={},
                handler=browser_mod.get_current_url,
                dangerous=False,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: browser недоступен (playwright не установлен).")

        # --- Мессенджеры ---
        try:
            from . import messenger as msg_mod
            self.register(ToolSpec(
                name="messenger.whatsapp_read",
                description="Прочитать последние сообщения из чата WhatsApp.",
                parameters={
                    "chat_name": "имя чата или контакта для поиска (обязательный)",
                    "count": "количество сообщений, по умолчанию 5 (необязательный)",
                },
                handler=msg_mod.whatsapp_get_messages,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="messenger.whatsapp_send",
                description="Отправить сообщение в чат WhatsApp. Требует голосового подтверждения.",
                parameters={
                    "chat_name": "имя чата или контакта (обязательный)",
                    "message": "текст сообщения (обязательный)",
                },
                handler=msg_mod.whatsapp_send_message,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="messenger.telegram_read",
                description="Прочитать последние сообщения из чата Telegram.",
                parameters={
                    "chat_name": "имя чата или контакта (обязательный)",
                    "count": "количество сообщений, по умолчанию 5 (необязательный)",
                },
                handler=msg_mod.telegram_get_messages,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: messenger недоступен (playwright не установлен).")

        # --- GUI Automation ---
        try:
            from . import gui as gui_mod
            self.register(ToolSpec(
                name="gui.mouse_pos",
                description="Получить текущие координаты курсора мыши на экране.",
                parameters={},
                handler=gui_mod.get_mouse_position,
                dangerous=False,
            ))
            self.register(ToolSpec(
                name="gui.mouse_move",
                description="Переместить мышь на указанные координаты x, y.",
                parameters={
                    "x": "координата X (обязательный)",
                    "y": "координата Y (обязательный)",
                    "duration": "время перемещения в секундах, по умолчанию 0.5"
                },
                handler=gui_mod.move_mouse,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="gui.click",
                description="Кликнуть мышью. Требует голосового подтверждения.",
                parameters={
                    "x": "координата X (необязательный, по умолчанию там где курсор)",
                    "y": "координата Y (необязательный)",
                    "button": "left, right или middle (по умолчанию left)",
                    "clicks": "количество кликов (по умолчанию 1)"
                },
                handler=gui_mod.click,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="gui.type",
                description="Ввести текст с клавиатуры. Требует голосового подтверждения.",
                parameters={"text": "текст для ввода (обязательный)"},
                handler=gui_mod.type_text,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="gui.press",
                description="Нажать клавишу (enter, esc, win и т.д.). Требует голосового подтверждения.",
                parameters={"key": "имя клавиши (обязательный)"},
                handler=gui_mod.press_key,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="gui.hotkey",
                description="Нажать сочетание клавиш (ctrl, c). Требует голосового подтверждения.",
                parameters={}, # В dispatcher не так просто передать *args через JSON параметры, сделаем обертку
                handler=lambda **kwargs: gui_mod.hotkey(*kwargs.values()),
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: gui недоступен (pyautogui не установлен).")

        # --- Vision (Анализ экрана) ---
        try:
            from . import vision as vision_mod
            self.register(ToolSpec(
                name="vision.analyze_screen",
                description="Сделать скриншот экрана и проанализировать, что на нём происходит.",
                parameters={"prompt": "вопрос о том, что нужно найти на экране (по умолчанию 'Что на экране?')"},
                handler=vision_mod.analyze_screen,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: vision недоступен.")

        # --- Email ---
        try:
            from . import email_tool as email_mod
            self.register(ToolSpec(
                name="email.read",
                description="Прочитать последние электронные письма (IMAP).",
                parameters={
                    "count": "количество писем (по умолчанию 5)",
                    "unread_only": "только непрочитанные (true/false, по умолчанию true)"
                },
                handler=email_mod.read_emails,
                dangerous=True,
            ))
            self.register(ToolSpec(
                name="email.send",
                description="Отправить электронное письмо (SMTP). Требует голосового подтверждения.",
                parameters={
                    "to_address": "email получателя (обязательный)",
                    "subject": "тема письма (обязательный)",
                    "body": "текст письма (обязательный)"
                },
                handler=email_mod.send_email,
                dangerous=True,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: email_tool недоступен.")

        # --- Task Planner ---
        # Регистрируем через замыкание, т.к. planner нужен сам dispatcher
        try:
            from . import planner as planner_mod

            def _run_plan(task: str) -> str:
                plan = planner_mod.create_plan(task, self)
                
                # Check for dangerous tools in the plan
                has_dangerous = False
                dangerous_tools = []
                for step in plan.steps:
                    spec = self.tools.get(step.tool)
                    if spec and spec.dangerous:
                        has_dangerous = True
                        dangerous_tools.append(step.tool)
                
                if has_dangerous:
                    from ..core.confirm import get_voice_confirm
                    vc = get_voice_confirm()
                    if vc is None:
                        import logging
                        logging.getLogger(__name__).error("ToolDispatcher: VoiceConfirm не инициализирован, опасный план отменен.")
                        return "Действие отменено: голосовое подтверждение недоступно, а план содержит опасные шаги."
                    
                    question = f"Сэр, план задачи '{task}' включает опасные инструменты: {', '.join(set(dangerous_tools))}. Разрешаете выполнение плана?"
                    if not vc.ask(question):
                        return "Действие отменено пользователем."

                return planner_mod.execute_plan(plan, self)

            self.register(ToolSpec(
                name="planner.run",
                description=(
                    "Выполнить сложную многошаговую задачу с автоматической декомпозицией. "
                    "Используй для задач вида: 'посмотри вотсап и найди дешевле', "
                    "'узнай погоду и открой новости'."
                ),
                parameters={"task": "полное описание задачи (обязательный)"},
                handler=_run_plan,
                dangerous=False,
            ))
        except ImportError:
            logger.warning("ToolDispatcher: planner недоступен.")

    # ──────────────────────────────────────────────────────────
    # Разбор ответа LLM
    # ──────────────────────────────────────────────────────────

    def parse_response(self, llm_response: str) -> ParsedResponse:
        """
        Определить тип ответа LLM: JSON tool_call или обычный текст.

        Поддерживаемые форматы JSON:
        1. Чистый JSON: {"action": "tool_call", "tool": "search", "params": {...}}
        2. JSON в markdown-блоке: ```json\n{"action": ...}\n```
        3. JSON в тексте (нечёткий поиск)

        Args:
            llm_response: Строка ответа LLM.

        Returns:
            ParsedResponse с type="tool_call" или type="text".
        """
        text = llm_response.strip()

        # 1. Прямой JSON
        json_str = self._extract_json(text)
        if json_str:
            tool_call = self._parse_tool_call_json(json_str)
            if tool_call:
                return ParsedResponse(type="tool_call", text=text, tool_call=tool_call)

        # 2. Обычный текст
        return ParsedResponse(type="text", text=text)

    def _extract_json(self, text: str) -> str | None:
        """Извлечь JSON-строку из текста (прямой или в markdown-блоке)."""
        stripped = text.strip()

        # Прямой JSON
        if stripped.startswith("{"):
            return stripped

        # JSON в markdown-блоке ```json ... ``` или ``` ... ```
        md_match = _JSON_MD_PATTERN.search(text)
        if md_match:
            return md_match.group(1).strip()

        # Попробовать найти { ... } в тексте
        brace_start = text.find("{")
        if brace_start != -1:
            brace_end = text.rfind("}")
            if brace_end > brace_start:
                candidate = text[brace_start:brace_end + 1]
                # Быстрая проверка — содержит tool_call
                if "tool_call" in candidate or "\"tool\"" in candidate:
                    return candidate

        return None

    def _parse_tool_call_json(self, json_str: str) -> ToolCall | None:
        """Разобрать JSON строку в ToolCall. Возвращает None при ошибке."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug("ToolDispatcher: не удалось разобрать JSON: %s", e)
            return None

        if not isinstance(data, dict):
            return None
        if data.get("action") != "tool_call":
            return None
        tool = data.get("tool", "")
        params = data.get("params", {})
        if not tool or not isinstance(tool, str):
            return None

        return ToolCall(tool=tool, params=params if isinstance(params, dict) else {})

    # ──────────────────────────────────────────────────────────
    # Выполнение инструмента
    # ──────────────────────────────────────────────────────────

    def execute(self, tool_call: ToolCall) -> str:
        """
        Выполнить вызов инструмента.

        Если инструмент помечен dangerous=True, запрашивает голосовое
        подтверждение через VoiceConfirm перед выполнением.

        Args:
            tool_call: Разобранный вызов инструмента.

        Returns:
            Строка результата для передачи обратно в LLM.
        """
        spec = self._tools.get(tool_call.tool)
        if not spec:
            available = ", ".join(self._tools.keys())
            logger.warning("ToolDispatcher: неизвестный инструмент %r", tool_call.tool)
            return (
                f"Ошибка: инструмент '{tool_call.tool}' не найден. "
                f"Доступные: {available}"
            )

        # Голосовое подтверждение для опасных инструментов
        if spec.dangerous:
            from ..core.confirm import get_voice_confirm
            vc = get_voice_confirm()
            if vc is None:
                logger.error("ToolDispatcher: VoiceConfirm не инициализирован, опасное действие отменено.")
                return (
                    "Действие отменено: голосовое подтверждение "
                    "недоступно, а инструмент помечен как опасный."
                )
            params_str = ", ".join(f"{k}={v!r}" for k, v in tool_call.params.items())
            question = (
                f"Сэр, хочу выполнить {spec.description.rstrip('.')} "
                f"с параметрами: {params_str}. Разрешаете?"
            )
            if not vc.ask(question):
                return "Действие отменено пользователем."

        # Выполнить инструмент
        logger.info("ToolDispatcher: выполняю %r с params=%r", tool_call.tool, tool_call.params)
        try:
            result = spec.handler(**tool_call.params)
            logger.info("ToolDispatcher: результат %r: %r", tool_call.tool, str(result)[:200])
            return str(result)
        except TypeError as e:
            logger.error("ToolDispatcher: неверные параметры для %r: %s", tool_call.tool, e)
            return f"Ошибка: неверные параметры для инструмента '{tool_call.tool}': {e}"
        except Exception as e:
            logger.error("ToolDispatcher: ошибка выполнения %r: %s", tool_call.tool, e)
            return f"Ошибка выполнения '{tool_call.tool}': {e}"

    # ──────────────────────────────────────────────────────────
    # Описание инструментов для системного промпта
    # ──────────────────────────────────────────────────────────

    def get_tools_prompt(self) -> str:
        """
        Сгенерировать описание всех инструментов для вставки в SYSTEM_PROMPT.

        Формат JSON tool_call, который ожидается от LLM:
        {"action": "tool_call", "tool": "<имя>", "params": {<параметры>}}
        """
        if not self._tools:
            return ""

        lines = ["Доступные инструменты (вызывай их через JSON tool_call):"]
        for name, spec in self._tools.items():
            params_desc = ", ".join(
                f"{k}: {v}" for k, v in spec.parameters.items()
            ) or "нет параметров"
            dangerous_mark = " ⚠️ (требует голосового подтверждения)" if spec.dangerous else ""
            lines.append(f"  - {name}{dangerous_mark}: {spec.description} Параметры: {{{params_desc}}}")

        lines.append(
            "\nДля вызова инструмента верни ТОЛЬКО валидный JSON без пояснений:\n"
            '{"action": "tool_call", "tool": "<имя>", "params": {<параметры>}}\n'
            "Для обычного текстового ответа — верни только текст без JSON."
        )
        return "\n".join(lines)

    @property
    def tools(self) -> dict[str, ToolSpec]:
        """Словарь зарегистрированных инструментов."""
        return dict(self._tools)
