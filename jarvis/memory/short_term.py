"""
Краткосрочная память — история текущего диалога.
Хранит последние N сообщений в collections.deque для быстрого доступа.
"""

from collections import deque
from typing import Any

from .. import config


class ShortTermMemory:
    """Хранит последние DIALOG_HISTORY_LIMIT сообщений диалога."""

    def __init__(self, limit: int | None = None) -> None:
        """Инициализация deque с лимитом из конфига."""
        self._limit = limit if limit is not None else config.DIALOG_HISTORY_LIMIT
        self._buffer: deque[dict[str, str]] = deque(maxlen=self._limit)

    @property
    def limit(self) -> int:
        """Публичный доступ к лимиту истории."""
        return self._limit

    def add(self, role: str, content: str, reasoning_details: dict[str, Any] | None = None) -> None:
        """Добавить сообщение в историю. role: 'user', 'assistant' или 'system'."""
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"role must be 'user', 'assistant' or 'system', got {role!r}")
        msg: dict[str, Any] = {"role": role, "content": content}
        if reasoning_details is not None:
            msg["reasoning_details"] = reasoning_details
        self._buffer.append(msg)

    def get_messages(self) -> list[dict[str, str]]:
        """Вернуть список сообщений для отправки в Claude API."""
        return list(self._buffer)

    def clear(self) -> None:
        """Полностью очистить историю диалога."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    def to_context_string(self) -> str:
        """
        Отформатировать историю для вставки в системный промпт.
        Используется как fallback / для отладки.
        """
        if not self._buffer:
            return "(история пуста)"
        lines: list[str] = []
        for msg in self._buffer:
            who = "Пользователь" if msg["role"] == "user" else "Джарвис"
            lines.append(f"{who}: {msg['content']}")
        return "\n".join(lines)

    def last_user(self) -> str | None:
        """Вернуть последнее сообщение пользователя или None."""
        for msg in reversed(self._buffer):
            if msg["role"] == "user":
                return msg["content"]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Сериализация для логирования / отладки."""
        return {
            "limit": self._limit,
            "size": len(self._buffer),
            "messages": list(self._buffer),
        }
