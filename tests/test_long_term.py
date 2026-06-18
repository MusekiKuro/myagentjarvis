"""Tests for LongTermMemory (jarvis.memory.long_term)."""
import pytest

from jarvis.memory.long_term import LongTermMemory


class TestLongTermMemory:
    """Tests for LongTermMemory CRUD operations."""

    def test_save_and_get_fact(self, long_term):
        """Save a fact and retrieve it."""
        long_term.save_fact("person", "name", "Алексей")
        facts = long_term.get_facts()
        assert len(facts) == 1
        assert facts[0]["category"] == "person"
        assert facts[0]["key"] == "name"
        assert facts[0]["value"] == "Алексей"

    def test_update_fact(self, long_term):
        """Saving same category+key twice should update, not duplicate."""
        long_term.save_fact("person", "name", "Алексей")
        long_term.save_fact("person", "name", "Дмитрий")
        facts = long_term.get_facts()
        assert len(facts) == 1
        assert facts[0]["value"] == "Дмитрий"

    def test_delete_fact(self, long_term):
        """Save then delete, verify gone."""
        long_term.save_fact("person", "name", "Тест")
        assert long_term.delete_fact("person", "name") is True
        facts = long_term.get_facts()
        assert len(facts) == 0

    def test_delete_nonexistent(self, long_term):
        """Deleting non-existent fact returns False."""
        result = long_term.delete_fact("nonexistent", "key")
        assert result is False

    def test_clear_all(self, long_term):
        """Save multiple, clear, verify empty."""
        long_term.save_fact("person", "name", "Тест")
        long_term.save_fact("preference", "likes", "кофе")
        long_term.save_fact("person", "age", "25")
        long_term.clear_all()
        assert long_term.get_facts() == []
        assert long_term.count() == 0

    def test_count(self, long_term):
        """Count returns correct number of facts."""
        assert long_term.count() == 0
        long_term.save_fact("person", "name", "Тест")
        long_term.save_fact("preference", "likes", "кофе")
        long_term.save_fact("person", "age", "30")
        assert long_term.count() == 3

    def test_to_context_string(self, long_term):
        """Formatted output includes category and key=value."""
        long_term.save_fact("person", "name", "Алексей")
        long_term.save_fact("preference", "likes", "кофе")
        result = long_term.to_context_string()
        assert "Известные факты о пользователе:" in result
        assert "name = Алексей" in result
        assert "likes = кофе" in result

    def test_to_context_string_empty(self, long_term):
        """Empty memory returns empty string."""
        assert long_term.to_context_string() == ""

    def test_get_facts_by_category(self, long_term):
        """Filtering facts by category."""
        long_term.save_fact("person", "name", "Тест")
        long_term.save_fact("preference", "likes", "кофе")
        long_term.save_fact("person", "age", "30")

        person_facts = long_term.get_facts(category="person")
        assert len(person_facts) == 2

        pref_facts = long_term.get_facts(category="preference")
        assert len(pref_facts) == 1
        assert pref_facts[0]["key"] == "likes"


class TestLongTermExtract:
    """Tests for extract_and_save pattern matching."""

    def test_extract_name(self, long_term):
        """'меня зовут Алексей' -> person/name/Алексей."""
        found = long_term.extract_and_save("меня зовут Алексей")
        assert len(found) >= 1
        assert ("person", "name", "Алексей") in found

    def test_extract_workplace(self, long_term):
        """'я работаю в Яндексе' -> person/workplace/Яндексе."""
        found = long_term.extract_and_save("я работаю в Яндексе")
        assert len(found) >= 1
        assert any(cat == "person" and key == "workplace" for cat, key, val in found)

    def test_extract_age(self, long_term):
        """'мне 30 лет' -> person/age/30."""
        found = long_term.extract_and_save("мне 30 лет")
        assert len(found) >= 1
        assert ("person", "age", "30") in found

    def test_extract_likes(self, long_term):
        """'я люблю кофе' -> preference/likes/кофе."""
        found = long_term.extract_and_save("я люблю кофе")
        assert len(found) >= 1
        assert ("preference", "likes", "кофе") in found

    def test_extract_dislikes(self, long_term):
        """'я не люблю чай' -> preference/dislikes/чай."""
        found = long_term.extract_and_save("я не люблю чай")
        assert len(found) >= 1
        assert ("preference", "dislikes", "чай") in found

    def test_extract_no_match(self, long_term):
        """'привет как дела' -> empty list (no patterns match)."""
        found = long_term.extract_and_save("привет как дела")
        assert found == []

    def test_extract_empty(self, long_term):
        """Empty string -> empty list."""
        found = long_term.extract_and_save("")
        assert found == []
