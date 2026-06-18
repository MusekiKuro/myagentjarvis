"""Tests for jarvis.core.executor module."""

import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from jarvis.core.executor import (
    open_app,
    open_url,
    run_command,
    run_python,
    parse_and_execute,
)


class TestOpenApp:
    """Tests for application opening helper."""

    @patch("os.system")
    @patch("subprocess.Popen")
    def test_open_app_known_protocol(self, mock_popen, mock_system):
        """Known apps with protocols should use os.system."""
        res = open_app("whatsapp")
        assert "Успешно запущено" in res
        mock_system.assert_called_once_with("start whatsapp:")
        mock_popen.assert_not_called()

    @patch("os.system")
    @patch("subprocess.Popen")
    def test_open_app_known_executable(self, mock_popen, mock_system):
        """Known apps with executables should use subprocess.Popen."""
        res = open_app("notepad")
        assert "Успешно запущено" in res
        mock_popen.assert_called_once_with("notepad.exe", shell=True)
        mock_system.assert_not_called()

    @patch("os.system")
    @patch("subprocess.Popen")
    def test_open_app_unknown(self, mock_popen, mock_system):
        """Unknown apps should fallback to trying subprocess.Popen."""
        res = open_app("my_custom_app.exe")
        assert "Успешно запущено" in res
        mock_popen.assert_called_once_with("my_custom_app.exe", shell=True)
        mock_system.assert_not_called()

    @patch("subprocess.Popen")
    def test_open_app_error(self, mock_popen):
        """Errors during launching should be captured and returned."""
        mock_popen.side_effect = OSError("File not found")
        res = open_app("nonexistent_app")
        assert "Ошибка при запуске" in res
        assert "File not found" in res


class TestOpenUrl:
    """Tests for URL opening helper."""

    @patch("webbrowser.open")
    def test_open_url_standard(self, mock_open):
        """Should open URL using webbrowser module."""
        res = open_url("https://google.com")
        assert "Успешно открыта ссылка" in res
        mock_open.assert_called_once_with("https://google.com")

    @patch("webbrowser.open")
    def test_open_url_auto_schema(self, mock_open):
        """Should prepended https:// if not present."""
        res = open_url("google.com")
        assert "https://google.com" in res
        mock_open.assert_called_once_with("https://google.com")

    @patch("webbrowser.open")
    def test_open_url_error(self, mock_open):
        """Should capture and return errors."""
        mock_open.side_effect = Exception("Browser error")
        res = open_url("google.com")
        assert "Ошибка открытия ссылки" in res
        assert "Browser error" in res


class TestRunCommand:
    """Tests for system command runner."""

    @patch("subprocess.run")
    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_command_success(self, mock_run):
        """Successful command should return stdout."""
        mock_process = MagicMock()
        mock_process.stdout = b"hello world\n"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        res = run_command("echo hello")
        assert "Вывод команды:" in res
        assert "hello world" in res

    @patch("subprocess.run")
    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_command_cp866_fallback(self, mock_run):
        """Should decode output in CP866 encoding if present."""
        mock_process = MagicMock()
        # CP866 bytes for Cyrillic 'Привет'
        mock_process.stdout = b"\x8f\xe0\xa8\xa2\xa5\xe2"
        mock_process.stderr = b""
        mock_run.return_value = mock_process

        res = run_command("echo Привет")
        assert "Привет" in res

    @patch("subprocess.run")
    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_command_timeout(self, mock_run):
        """Should return timeout error message."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=15)
        res = run_command("sleep 20")
        assert "превышен тайм-аут" in res


class TestRunPython:
    """Tests for Python code runner."""

    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_python_print(self):
        """Python print should capture stdout."""
        code = "print(10 + 20)"
        res = run_python(code)
        assert res == "30"

    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_python_variables_fallback(self):
        """If no stdout, should return local variables."""
        code = "x = 42\ny = 'hello'"
        res = run_python(code)
        assert "Локальные переменные" in res
        assert "'x': 42" in res
        assert "'y': 'hello'" in res

    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_python_no_output_no_vars(self):
        """If no output and no variables, should return success message."""
        code = "pass"
        res = run_python(code)
        assert "успешно без вывода" in res

    @patch("jarvis.config.REQUIRE_ACTION_CONFIRMATION", False)
    def test_run_python_error(self):
        """Syntax and runtime errors should return traceback."""
        code = "1 / 0"
        res = run_python(code)
        assert "Ошибка выполнения Python-кода" in res
        assert "ZeroDivisionError" in res


class TestParseAndExecute:
    """Tests for tag parsing orchestrator."""

    @patch("jarvis.core.executor.open_app")
    @patch("jarvis.core.executor.open_url")
    def test_parse_and_execute_order(self, mock_url, mock_app):
        """Tags should be parsed and executed in exact appearance order."""
        mock_app.return_value = "App Ok"
        mock_url.return_value = "Url Ok"

        text = "Open this: <open_app>notepad</open_app> and go here: <open_url>youtube.com</open_url>"
        results = parse_and_execute(text)

        assert len(results) == 2
        assert results[0]["type"] == "open_app"
        assert results[0]["param"] == "notepad"
        assert results[0]["result"] == "App Ok"

        assert results[1]["type"] == "open_url"
        assert results[1]["param"] == "youtube.com"
        assert results[1]["result"] == "Url Ok"

    @patch("jarvis.memory.long_term.LongTermMemory")
    def test_parse_and_execute_save_fact(self, mock_ltm_class):
        """Should parse <save_fact> tag and call LongTermMemory.save_fact."""
        mock_ltm = MagicMock()
        mock_ltm_class.return_value.__enter__.return_value = mock_ltm

        text = 'Запоминаю: <save_fact category="preference" key="food">pizza</save_fact>'
        results = parse_and_execute(text)

        assert len(results) == 1
        assert results[0]["type"] == "save_fact"
        assert results[0]["param"] == "('preference', 'food', 'pizza')"
        assert "Факт сохранён" in results[0]["result"]
        mock_ltm.save_fact.assert_called_once_with("preference", "food", "pizza")
