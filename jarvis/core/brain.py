"""
Мозг ассистента: общение с OpenRouter API + управление историей диалога.
Использует requests для API запросов и поддерживает reasoning.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .. import config
from ..memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


# Системный промпт — базовая часть (характер, стиль общения)
SYSTEM_PROMPT = (
    "Ты — Джарвис, персональный голосовой ассистент и управляющий компьютера Сэра. "
    "Веди себя как профессиональный дворецкий высшего класса. "
    "Правила общения:\n"
    "1. Всегда обращайся к пользователю 'Сэр'.\n"
    "2. Отвечай КРАТКО — максимум 2-3 предложения. Ответы озвучиваются вслух.\n"
    "3. Будь точен и информативен, избегай воды.\n"
    "4. Язык — только русский.\n"
    "5. Начинай ответ сразу с сути, не с приветствия.\n"
    "\n"
    "Ты умеешь не только отвечать, но и выполнять задачи на компьютере Сэра через инструменты.\n"
    "Когда задача требует действия (поиск, открыть файл, запустить программу, управить системой) — вызывай инструмент.\n"
    "Для вызова инструмента верни ТОЛЬКО валидный JSON без пояснений и без текста вокруг:\n"
    '{"action": "tool_call", "tool": "<имя>", "params": {<параметры>}}\n'
    "Для обычного текстового ответа — верни только текст без JSON.\n"
    "\n"
    "Также доступны XML-теги для быстрых действий:\n"
    "  - `<save_fact category=\"категория\" key=\"ключ\">значение</save_fact>` — Сохранить факт (категории: person, preference).\n"
    "Примеры стиля:\n"
    "  'Сэр, нахожу результаты.'  ← при вызове tool: {\"action\": \"tool_call\", \"tool\": \"search\", \"params\": {\"query\": \"...\"}}\n"
    "  'Сэр, запомнил. <save_fact category=\"preference\" key=\"color\">красный</save_fact>'  ← при сохранении факта"
)


class Brain:
    """Управляет общением с OpenRouter API и историей диалога."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        short_term: ShortTermMemory | None = None,
    ) -> None:
        self._api_key = api_key or config.OPENROUTER_API_KEY
        if not self._api_key or self._api_key == "sk-or-v1-your-key-here":
            raise ValueError(
                "OPENROUTER_API_KEY не задан или равен шаблону. "
                "Укажите ключ в .env (получить на https://openrouter.ai)"
            )

        self._model = model or config.OPENROUTER_MODEL
        self._max_tokens = max_tokens or config.OPENROUTER_MAX_TOKENS
        self._short_term = short_term or ShortTermMemory()
        self._last_reasoning: str = ""  # Bug B3 fix: сохраняется из _stream_api

        logger.info(
            "Brain: инициализирован (model=%s, max_tokens=%d, history_limit=%d)",
            self._model,
            self._max_tokens,
            self._short_term.limit,
        )

    # ──────────────────────────────────────────────────────────
    # Управление историями
    # ──────────────────────────────────────────────────────────
    @property
    def history(self) -> ShortTermMemory:
        return self._short_term

    def clear_history(self) -> None:
        self._short_term.clear()
        logger.info("Brain: история диалога очищена")

    # ──────────────────────────────────────────────────────────
    # Системный промпт с учётом long-term памяти
    # ──────────────────────────────────────────────────────────
    def _build_system_prompt(self, long_term_context: str = "", tools_prompt: str = "") -> str:
        parts = [SYSTEM_PROMPT]
        if tools_prompt:
            parts.append(tools_prompt)
        if long_term_context:
            parts.append(long_term_context)
        return "\n\n".join(parts)

    # ──────────────────────────────────────────────────────────
    # Низкоуровневый вызов API (без побочных эффектов на историю)
    # ──────────────────────────────────────────────────────────
    def _call_api(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
    ) -> Any:
        """Сырой вызов OpenRouter API. Возвращает генератор (для stream) или tuple (content, reasoning_details)."""
        if stream:
            return self._stream_api(system_prompt, messages)
        return self._blocking_api(system_prompt, messages)

    def _stream_api(
        self, system_prompt: str, messages: list[dict[str, Any]]
    ) -> Any:
        """Streaming-вариант: возвращает генератор, который yield'ит чанки текста."""
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "reasoning": {"enabled": True},
            "stream": True,
            "max_tokens": self._max_tokens,  # Bug B1 fix
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jarvis",
            "X-Title": "JARVIS Assistant"
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30,
        )
        response.raise_for_status()
        response.encoding = 'utf-8'

        reasoning_chunks: list[str] = []

        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if data.get("choices"):
                        delta = data["choices"][0].get("delta", {})
                        if delta.get("content"):
                            yield delta["content"]
                        if delta.get("reasoning"):
                            reasoning_chunks.append(delta["reasoning"])
                except json.JSONDecodeError:
                    pass

        # Bug B3 fix: сохраняем reasoning в атрибут, чтобы не потерять при генераторе
        if reasoning_chunks:
            self._last_reasoning = "".join(reasoning_chunks).strip()
            logger.debug("Brain._stream_api: reasoning %d символов", len(self._last_reasoning))

    def _blocking_api(
        self, system_prompt: str, messages: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any] | None]:
        """Не-streaming вариант. Возвращает (content, reasoning_details)."""
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "reasoning": {"enabled": True},
            "stream": False,
            "max_tokens": self._max_tokens,  # Bug B1 fix
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jarvis",
            "X-Title": "JARVIS Assistant"
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()
        if "choices" not in data or not data["choices"]:
            return "", None

        message = data["choices"][0].get("message", {})
        content = message.get("content", "").strip()
        reasoning_details = message.get("reasoning_details")

        return content, reasoning_details

    # ──────────────────────────────────────────────────────────
    # Главный метод — получить ответ
    # ──────────────────────────────────────────────────────────
    def get_response(
        self,
        user_text: str,
        long_term_context: str = "",
        tools_prompt: str = "",
        stream: bool | None = None,
    ) -> str:
        """
        Отправить user_text в OpenRouter и вернуть ответ (строкой).
        """
        if not user_text or not user_text.strip():
            return ""

        use_stream = config.OPENROUTER_STREAM if stream is None else stream

        self._short_term.add("user", user_text)

        system_prompt = self._build_system_prompt(long_term_context, tools_prompt)
        messages = self._short_term.get_messages()

        logger.debug(
            "Brain.get_response: stream=%s, messages=%d, sys_len=%d",
            use_stream,
            len(messages),
            len(system_prompt),
        )

        try:
            result = self._call_api(system_prompt, messages, stream=use_stream)
        except Exception as e:
            logger.error("Brain.get_response: ошибка API: %s", e)
            return self._handle_api_error(e)

        if use_stream:
            # Если это стрим, мы возвращаем генератор как есть.
            # Внимание: history обновится снаружи, когда генератор исчерпается,
            # либо мы можем сделать обертку-генератор.
            def generator_wrapper():
                full_text = []
                for chunk in result:
                    full_text.append(chunk)
                    yield chunk
                self._short_term.add("assistant", "".join(full_text).strip())
            return generator_wrapper()
        else:
            full_response, reasoning = result
            if full_response:
                self._short_term.add("assistant", full_response, reasoning_details=reasoning)
            return full_response

    def _handle_api_error(self, err: Exception) -> str:
        """Fallback-сообщение для пользователя при сбое API."""
        msg = str(err).lower()
        if "401" in msg or "unauthorized" in msg:
            return "Сэр, ключ API недействителен. Проверьте OPENROUTER_API_KEY."
        if "402" in msg or "payment" in msg:
            return "Сэр, на балансе OpenRouter закончились средства."
        if "rate limit" in msg or "429" in msg:
            return "Сэр, слишком много запросов. Подождите секунду."
        if "timeout" in msg or "timed out" in msg:
            return "Сэр, нет связи с сервером. Проверьте интернет."
        return "Сэр, не удалось получить ответ от сервера."

    # ──────────────────────────────────────────────────────────
    # Retry-обёртка для main.py
    # ──────────────────────────────────────────────────────────
    def get_response_with_retry(
        self,
        user_text: str,
        long_term_context: str = "",
        tools_prompt: str = "",
        max_attempts: int = 3,
        stream: bool = False,
    ) -> Any:
        """До 3 попыток запроса, потом fallback. Поддерживает стриминг."""
        if not user_text or not user_text.strip():
            return ""

        # Добавляем сообщение пользователя ОДИН раз, ДО цикла
        self._short_term.add("user", user_text)
        system_prompt = self._build_system_prompt(long_term_context, tools_prompt)

        last_err: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                messages = self._short_term.get_messages()
                if stream:
                    # Для стриминга мы делаем вызов и возвращаем обертку
                    # Retry для стриминга сложнее, если он упадет посередине, но мы хотя бы ловим начальные ошибки.
                    result = self._stream_api(system_prompt, messages)

                    def generator_wrapper():
                        full_text = []
                        for chunk in result:
                            full_text.append(chunk)
                            yield chunk
                        self._short_term.add("assistant", "".join(full_text).strip())
                    return generator_wrapper()
                else:
                    full_response, reasoning = self._blocking_api(system_prompt, messages)
                    if full_response:
                        self._short_term.add("assistant", full_response, reasoning_details=reasoning)
                        return full_response
                logger.warning(
                    "Brain.get_response_with_retry: попытка %d — пустой ответ",
                    attempt,
                )
            except Exception as e:
                last_err = e
                logger.warning(
                    "Brain.get_response_with_retry: попытка %d не удалась: %s",
                    attempt,
                    e,
                )
        return self._handle_api_error(last_err) if last_err else "Сэр, нет связи с сервером."
