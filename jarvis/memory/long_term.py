"""
Долгосрочная память — факты о пользователе в SQLite.
Ассистент запоминает имя, профессию, предпочтения и т.п.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from .. import config

logger = logging.getLogger(__name__)


# SQL-схема таблицы фактов
_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,   -- 'preference', 'person', 'task', 'fact'
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# SQL-схема таблицы истории задач (Фаза 2)
_TASK_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,              -- исходная задача пользователя
    steps_count INTEGER DEFAULT 0,  -- количество выполненных шагов
    result_summary TEXT,            -- краткое резюме результата
    status TEXT DEFAULT 'completed', -- 'completed' | 'partial' | 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class LongTermMemory:
    """Долгосрочная память о пользователе на SQLite."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else config.LONG_TERM_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()
        self._init_db()

    # ──────────────────────────────────────────────────────────
    # Внутреннее
    # ──────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        """Create (or reconnect) a SQLite connection with WAL mode."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """Создать таблицы facts и task_history, если их ещё нет."""
        try:
            self._conn.executescript(_SCHEMA)
            self._conn.executescript(_TASK_HISTORY_SCHEMA)
            self._conn.commit()
            logger.debug("LongTermMemory: БД инициализирована (%s)", self._db_path)
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка инициализации БД: %s", e)
            raise

    def close(self) -> None:
        """Закрыть соединение с БД."""
        try:
            self._conn.close()
        except Exception as e:
            logger.warning("LongTermMemory: ошибка закрытия БД: %s", e)

    def __enter__(self) -> LongTermMemory:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ──────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────
    def save_fact(self, category: str, key: str, value: str) -> None:
        """Сохранить или обновить факт (по уникальной паре category+key)."""
        try:
            conn = self._conn
            # Сначала проверяем, есть ли уже запись с такой парой (category, key)
            existing = conn.execute(
                "SELECT id FROM facts WHERE category = ? AND key = ?",
                (category, key),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE facts
                    SET value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (value, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO facts (category, key, value)
                    VALUES (?, ?, ?)
                    """,
                    (category, key, value),
                )
            conn.commit()
            logger.info(
                "LongTermMemory: сохранён факт [%s/%s] = %s",
                category,
                key,
                value,
            )
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка сохранения факта: %s", e)

    def get_facts(self, category: str | None = None) -> list[dict[str, Any]]:
        """Получить список фактов (опционально фильтр по категории)."""
        try:
            conn = self._conn
            if category:
                rows = conn.execute(
                    "SELECT * FROM facts WHERE category = ? ORDER BY key",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM facts ORDER BY category, key"
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка чтения фактов: %s", e)
            return []

    def delete_fact(self, category: str, key: str) -> bool:
        """Удалить факт. Возвращает True если что-то удалено."""
        try:
            conn = self._conn
            cur = conn.execute(
                "DELETE FROM facts WHERE category = ? AND key = ?",
                (category, key),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка удаления факта: %s", e)
            return False

    def clear_all(self) -> None:
        """Полностью очистить все факты (для отладки)."""
        try:
            conn = self._conn
            conn.execute("DELETE FROM facts")
            conn.commit()
            logger.warning("LongTermMemory: вся память очищена")
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка очистки: %s", e)

    # ──────────────────────────────────────────────────────────────
    # История задач (Фаза 2)
    # ──────────────────────────────────────────────────────────────
    def save_task(
        self,
        task: str,
        steps_count: int = 0,
        result_summary: str = "",
        status: str = "completed",
    ) -> None:
        """Сохранить запись о выполненной задаче в task_history."""
        try:
            self._conn.execute(
                """
                INSERT INTO task_history (task, steps_count, result_summary, status)
                VALUES (?, ?, ?, ?)
                """,
                (task, steps_count, result_summary, status),
            )
            self._conn.commit()
            logger.info("LongTermMemory: задача сохранена: %r (статус=%s)", task[:60], status)
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка сохранения задачи: %s", e)

    def get_task_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Получить последние N выполненных задач из task_history."""
        try:
            rows = self._conn.execute(
                """
                SELECT task, steps_count, result_summary, status, created_at
                FROM task_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка чтения task_history: %s", e)
            return []

    def clear_task_history(self) -> None:
        """Очистить историю задач."""
        try:
            self._conn.execute("DELETE FROM task_history")
            self._conn.commit()
            logger.warning("LongTermMemory: история задач очищена")
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка очистки task_history: %s", e)

    # ──────────────────────────────────────────────────────────────
    # Контекст для промпта
    # ──────────────────────────────────────────────────────────────
    def to_context_string(self) -> str:
        """Отформатировать все факты и последние задачи в строку для системного промпта."""
        parts = []

        # Факты о пользователе
        facts = self.get_facts()
        if facts:
            lines = ["Известные факты о пользователе:"]
            by_cat: dict[str, list[dict[str, Any]]] = {}
            for f in facts:
                by_cat.setdefault(f["category"], []).append(f)
            for cat, items in by_cat.items():
                lines.append(f"- {cat}:")
                for item in items:
                    lines.append(f"    • {item['key']} = {item['value']}")
            parts.append("\n".join(lines))

        # Последние задачи (до 5)
        tasks = self.get_task_history(limit=5)
        if tasks:
            lines = ["Недавно выполненные задачи:"]
            for t in tasks:
                ts = t.get("created_at", "")[:16]  # YYYY-MM-DD HH:MM
                lines.append(f"  [{ts}] {t['task']} → {t['result_summary'][:80]}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    # ──────────────────────────────────────────────────────────
    # Статистика
    # ──────────────────────────────────────────────────────────
    def count(self) -> int:
        """Количество сохранённых фактов."""
        try:
            conn = self._conn
            row = conn.execute("SELECT COUNT(*) AS c FROM facts").fetchone()
            return int(row["c"]) if row else 0
        except sqlite3.Error as e:
            logger.error("LongTermMemory: ошибка count: %s", e)
            return 0
