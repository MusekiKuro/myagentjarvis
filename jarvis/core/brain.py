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


# Системный промпт — передаётся дословно
SYSTEM_PROMPT = (
    "Ты — Джарвис, персональный голосовой ассистент и управляющий компьютера Сэра. "
    "Веди себя как профессиональный дворецкий высшего класса. "
    "Правила общения:\n"
    "1. Всегда обращайся к пользователю 'Сэр'.\n"
    "2. Отвечай КРАТКО — максимум 2-3 предложения. Ответы озвучиваются вслух.\n"
    "3. Будь точен и информативен, избегай воды.\n"
    "4. Язык — только русский.\n"
    "5. Начинай ответ сразу с сути, не с приветствия.\n"
    "6. Для управления компьютером Сэра используй специальные XML-теги. Вставляй их прямо в ответ. Они будут выполнены локально.\n"
    "Доступные действия (XML-теги):\n"
    "  - `<open_app>имя_приложения</open_app>` — Открыть программу (whatsapp, telegram, notepad, calc, explorer).\n"
    "  - `<open_url>ссылка</open_url>` — Открыть ссылку в браузере (например, <open_url>youtube.com</open_url>).\n"
    "  - `<run_command>команда</run_command>` — Выполнить команду терминала Windows (cmd/powershell).\n"
    "  - `<python_code>код_python</python_code>` — Выполнить Python-код для вычислений, работы с файлами, автоматизации. Вывод (stdout/переменные) вернется тебе следующим сообщением.\n"
    "  - `<save_fact category=\"категория\" key=\"ключ\">значение</save_fact>` — Сохранить факт о пользователе в долговременную память (категории: person, preference).\n"
    "Правило тегов: Если нужно выполнить действие, ОБЯЗАТЕЛЬНО пиши соответствующий тег. Можешь комбинировать теги.\n"
    "Примеры стиля:\n"
    "  'Сэр, запускаю WhatsApp. <open_app>whatsapp</open_app>'\n"
    "  'Сэр, открываю YouTube. <open_url>youtube.com</open_url>'\n"
    "  'Сэр, запомнил ваш любимый цвет. <save_fact category=\"preference\" key=\"color\">красный</save_fact>'\n"
    "  'Сэр, выполняю вычисления. <python_code>print(256 * 1024)</python_code>'"
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
    def _build_system_prompt(self, long_term_context: str = "") -> str:
        if long_term_context:
            return f"{SYSTEM_PROMPT}\n\n{long_term_context}"
        return SYSTEM_PROMPT

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

        reasoning_chunks: list[str] = []

        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if "choices" in data and data["choices"]:
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                        if "reasoning" in delta and delta["reasoning"]:
                            reasoning_chunks.append(delta["reasoning"])
                except json.JSONDecodeError:
                    pass

        # Мы не возвращаем reasoning_details напрямую из генератора, 
        # но генератор yield'ит только content. 
        # Для простоты в стриминге мы игнорируем reasoning в ответе (или его можно вернуть хитрым способом).

    def _blocking_api(
        self, system_prompt: str, messages: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any] | None]:
        """Не-streaming вариант. Возвращает (content, reasoning_details)."""
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "reasoning": {"enabled": True},
            "stream": False,
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
        stream: bool | None = None,
    ) -> str:
        """
        Отправить user_text в OpenRouter и вернуть ответ (строкой).
        """
        if not user_text or not user_text.strip():
            return ""

        use_stream = config.OPENROUTER_STREAM if stream is None else stream

        self._short_term.add("user", user_text)

        system_prompt = self._build_system_prompt(long_term_context)
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
        max_attempts: int = 3,
        stream: bool = False,
    ) -> Any:
        """До 3 попыток запроса, потом fallback. Поддерживает стриминг."""
        if not user_text or not user_text.strip():
            return ""

        # Добавляем сообщение пользователя ОДИН раз, ДО цикла
        self._short_term.add("user", user_text)
        system_prompt = self._build_system_prompt(long_term_context)

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