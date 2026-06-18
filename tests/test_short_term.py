"""Тесты ShortTermMemory."""
import pytest


class TestShortTermMemory:
    """Тесты краткосрочной памяти."""

    def test_add_and_get(self, short_term):
        short_term.add("user", "Привет")
        short_term.add("assistant", "Здравствуйте, Сэр.")
        messages = short_term.get_messages()
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Привет"}
        assert messages[1] == {"role": "assistant", "content": "Здравствуйте, Сэр."}

    def test_limit_enforcement(self, short_term):
        """При превышении лимита старые сообщения удаляются."""
        for i in range(15):
            short_term.add("user", f"msg-{i}")
        messages = short_term.get_messages()
        # Лимит short_term fixture = 10
        assert len(messages) == 10
        assert messages[0]["content"] == "msg-5"
        assert messages[-1]["content"] == "msg-14"

    def test_clear(self, short_term):
        short_term.add("user", "test")
        short_term.add("assistant", "reply")
        short_term.clear()
        assert len(short_term) == 0
        assert short_term.get_messages() == []

    def test_invalid_role(self, short_term):
        with pytest.raises(ValueError, match="role must be"):
            short_term.add("invalid_role", "test")

    def test_last_user(self, short_term):
        short_term.add("user", "first")
        short_term.add("assistant", "reply")
        short_term.add("user", "second")
        assert short_term.last_user() == "second"

    def test_last_user_empty(self, short_term):
        assert short_term.last_user() is None

    def test_to_context_string(self, short_term):
        short_term.add("user", "Привет")
        short_term.add("assistant", "Здравствуйте")
        ctx = short_term.to_context_string()
        assert "Пользователь: Привет" in ctx
        assert "Джарвис: Здравствуйте" in ctx

    def test_to_context_string_empty(self, short_term):
        assert short_term.to_context_string() == "(история пуста)"

    def test_limit_property(self, short_term):
        assert short_term.limit == 10

    def test_limit_zero_uses_config_default(self):
        """limit=0 не должен вызывать ошибку (deque(maxlen=0) — пустой)."""
        from jarvis.memory.short_term import ShortTermMemory
        mem = ShortTermMemory(limit=0)
        assert mem.limit == 0
        # deque с maxlen=0 не может хранить элементы
        mem.add("user", "test")
        assert len(mem) == 0

    def test_to_dict(self, short_term):
        short_term.add("user", "test")
        d = short_term.to_dict()
        assert d["limit"] == 10
        assert d["size"] == 1
        assert len(d["messages"]) == 1
        assert d["messages"][0]["role"] == "user"

    def test_len(self, short_term):
        assert len(short_term) == 0
        short_term.add("user", "a")
        assert len(short_term) == 1
        short_term.add("assistant", "b")
        assert len(short_term) == 2

    def test_add_reasoning_details(self, short_term):
        reasoning = {"reasoning": "I am thinking..."}
        short_term.add("assistant", "Hello", reasoning_details=reasoning)
        messages = short_term.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello"
        assert messages[0]["reasoning_details"] == reasoning
