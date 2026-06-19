"""
Тесты на исправления багов из аудита.
"""

from unittest.mock import MagicMock, patch

from jarvis.tools.dispatcher import ToolDispatcher, ToolCall, ToolSpec
from jarvis.core.brain import Brain
from jarvis.tools.planner import execute_plan, ExecutionPlan, PlanStep

def test_dispatcher_fail_closed_dangerous():
    """Предотвращает регрессию: fail-open сценарий при VoiceConfirm=None для опасных инструментов."""
    dispatcher = ToolDispatcher()
    
    # Регистрация фейкового опасного инструмента
    def fake_handler(**kwargs):
        return "Успех"
        
    dispatcher.register(ToolSpec(
        name="fake.dangerous",
        description="Фейковый опасный",
        parameters={},
        handler=fake_handler,
        dangerous=True,
    ))
    
    tc = ToolCall(tool="fake.dangerous", params={})
    
    # Мокаем get_voice_confirm чтобы возвращал None
    with patch("jarvis.core.confirm.get_voice_confirm", return_value=None):
        result = dispatcher.execute(tc)
        
    assert "Действие отменено" in result
    assert "недоступно" in result

def test_brain_tools_prompt_passed():
    """Предотвращает регрессию: tools_prompt не передавался в реальный API-запрос."""
    brain = Brain(api_key="sk-or-v1-fake-key", model="fake-model")
    
    with patch.object(brain, "_blocking_api", return_value=("Ответ", None)) as mock_api:
        brain.get_response_with_retry(
            user_text="Привет",
            tools_prompt="СПИСОК_ИНСТРУМЕНТОВ_123",
            stream=False
        )
        
        # Проверяем, что в system prompt попал tools_prompt
        args, kwargs = mock_api.call_args
        system_prompt = args[0]
        assert "СПИСОК_ИНСТРУМЕНТОВ_123" in system_prompt

def test_planner_step_error_marked():
    """Предотвращает регрессию: planner.run должен явно помечать шаг как failed при ошибке и останавливать план."""
    dispatcher = ToolDispatcher()
    
    plan = ExecutionPlan(
        task="Тест ошибки",
        steps=[
            PlanStep(step_num=1, tool="fake.fail", params={}),
            PlanStep(step_num=2, tool="fake.success", params={})
        ]
    )
    
    # Мокаем execute так, чтобы на первом шаге падало, а на втором (если дойдет) возвращало ок
    def mock_execute(tc):
        if tc.tool == "fake.fail":
            raise Exception("Имитация ошибки инструмента")
        return "ОК"
        
    with patch("jarvis.tools.planner._summarize_results", return_value="Суммаризация") as mock_summarize:
        with patch.object(dispatcher, "execute", side_effect=mock_execute) as mock_exec:
            execute_plan(plan, dispatcher, stop_on_error=True)
            
            # Проверяем, что execute был вызван ровно 1 раз
            assert mock_exec.call_count == 1
            
            # Проверяем, что в суммаризацию ушёл флаг partial=True
            mock_summarize.assert_called_once()
            _, kwargs = mock_summarize.call_args
            assert kwargs.get("partial") is True
            assert kwargs.get("stopped_at") == 1
        
    assert plan.steps[0].error == "Имитация ошибки инструмента"
    assert plan.steps[0].result is None
    # Второй шаг не должен выполниться
    assert plan.steps[1].result is None
    assert plan.steps[1].error is None

def test_planner_no_ltm_logged(caplog):
    """Предотвращает регрессию: planner.run без ltm должен явно логировать что не сохранён."""
    dispatcher = ToolDispatcher()
    plan = ExecutionPlan(
        task="Тест ltm",
        steps=[PlanStep(step_num=1, tool="text_response", params={"answer": "ok"})]
    )
    
    import logging
    caplog.set_level(logging.INFO)
    with patch("jarvis.tools.planner._summarize_results", return_value="Суммаризация"):
        execute_plan(plan, dispatcher, ltm=None)
        
    assert "ltm не передан" in caplog.text

import pytest

@pytest.mark.parametrize("tool_name", [
    "apps.open_app",
    "apps.close_app",
    "browser.click",
    "browser.fill",
    "clipboard.set",
    "email.read",
    "vision.analyze_screen"
])
def test_dangerous_classification(tool_name):
    """Предотвращает регрессию: чувствительные инструменты должны иметь dangerous=True."""
    dispatcher = ToolDispatcher()
    spec = dispatcher.tools.get(tool_name)
    if spec:
        assert spec.dangerous is True

@pytest.fixture
def voice_confirm():
    from jarvis.core.confirm import VoiceConfirm
    from jarvis.core.stt import SpeechToText
    from jarvis.core.tts import TextToSpeech
    
    vc = VoiceConfirm(tts=MagicMock(), stt=MagicMock(), speak_fn=MagicMock())
    return vc

@pytest.mark.parametrize("text, expected", [
    ("да", True),
    ("не надо", False),
    ("не давай", False),
    ("ни в коем случае", False),
    ("давай делай", True),
    ("отказываю", False),
    ("какой-то шум", None),
    ("", False)
])
def test_voice_confirm_parsing(voice_confirm, text, expected):
    """Предотвращает регрессию: отказ должен иметь приоритет над подтверждением, и должны использоваться границы слов."""
    voice_confirm._stt.transcribe = MagicMock(return_value=text)
    
    with patch("jarvis.core.listener.record_until_silence", return_value=b"audio"):
        result = voice_confirm._listen_and_parse()
        assert result is expected

@pytest.mark.parametrize("tool_name", [
    "messenger.whatsapp_read",
    "messenger.telegram_read",
    "browser.open",
    "browser.screenshot",
    "gui.mouse_move",
    "system.set_volume",
    "system.set_brightness",
])
def test_newly_classified_dangerous(tool_name):
    """Регрессия: эти инструменты были dangerous=False до раунда 3."""
    dispatcher = ToolDispatcher()
    spec = dispatcher.tools.get(tool_name)
    if spec:
        assert spec.dangerous is True

def test_legacy_executor_fail_closed():
    """Предотвращает регрессию: legacy XML executor должен использовать fail-closed логику и не зависать на input()."""
    from jarvis.core.executor import run_command
    import jarvis.config as config
    
    # Эмулируем отсутствие голосового подтверждения
    with patch("jarvis.core.executor._voice_confirm", None):
        # Настраиваем конфиг чтобы требовал подтверждения
        original_req = config.REQUIRE_ACTION_CONFIRMATION
        config.REQUIRE_ACTION_CONFIRMATION = True
        try:
            # Вызываем run_command. Если он попытается сделать input(), тест повиснет (или pytest бросит IOError).
            # Мы ожидаем, что он сразу вернёт отказ.
            result = run_command("echo malicious")
            assert "Действие отменено" in result
            assert "недоступно" in result
        finally:
            config.REQUIRE_ACTION_CONFIRMATION = original_req

def test_apps_open_app_allowlist():
    """Предотвращает регрессию: apps.open_app должен использовать allowlist и не делать shell=True."""
    from jarvis.tools.apps import open_app
    
    # 1. Запуск разрешенного приложения
    with patch("subprocess.Popen") as mock_popen:
        res = open_app("блокнот")
        assert "Приложение запущено: блокнот" in res
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert kwargs.get("shell") is False
        assert isinstance(args[0], list)
        assert args[0][0] == "notepad.exe"
        
    # 2. Запуск неизвестного приложения (shell injection attempt)
    with patch("subprocess.Popen") as mock_popen:
        res = open_app("calc.exe & del /f /q C:\\*")
        assert "Не знаю приложение" in res
        mock_popen.assert_not_called()
        
    # 3. Запуск похожего имени (substring injection attempt)
    with patch("subprocess.Popen") as mock_popen:
        res = open_app("блокнот; rm -rf /")
        assert "Не знаю приложение" in res
        mock_popen.assert_not_called()
