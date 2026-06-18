import pytest
from jarvis.tools.dispatcher import ToolDispatcher, ToolSpec

def test_dispatcher_parse_text():
    dispatcher = ToolDispatcher()
    
    # Обычный текст
    text = "Сэр, вот ваш результат."
    res = dispatcher.parse_response(text)
    assert res.type == "text"
    assert res.text == text
    assert res.tool_call is None

def test_dispatcher_parse_json():
    dispatcher = ToolDispatcher()
    
    # Прямой JSON
    json_str = '{"action": "tool_call", "tool": "search", "params": {"query": "test"}}'
    res = dispatcher.parse_response(json_str)
    assert res.type == "tool_call"
    assert res.tool_call is not None
    assert res.tool_call.tool == "search"
    assert res.tool_call.params == {"query": "test"}
    
    # JSON в markdown
    md_str = '```json\n{"action": "tool_call", "tool": "files.list_dir", "params": {}}\n```'
    res2 = dispatcher.parse_response(md_str)
    assert res2.type == "tool_call"
    assert res2.tool_call.tool == "files.list_dir"
    assert res2.tool_call.params == {}
    
    # Текст + JSON (нечеткий)
    mixed = 'Я ищу это.\n{"action": "tool_call", "tool": "sys", "params": {}}\nПодождите.'
    res3 = dispatcher.parse_response(mixed)
    assert res3.type == "tool_call"
    assert res3.tool_call.tool == "sys"

def test_dispatcher_execute():
    dispatcher = ToolDispatcher()
    
    # Регистрируем мок-инструмент
    def mock_handler(name: str):
        return f"Hello, {name}!"
        
    dispatcher.register(ToolSpec(
        name="hello",
        description="test",
        parameters={},
        handler=mock_handler,
        dangerous=False
    ))
    
    from jarvis.tools.dispatcher import ToolCall
    res = dispatcher.execute(ToolCall(tool="hello", params={"name": "World"}))
    assert res == "Hello, World!"

def test_dispatcher_execute_dangerous():
    dispatcher = ToolDispatcher()
    
    def mock_dangerous():
        return "boom"
        
    dispatcher.register(ToolSpec(
        name="boom",
        description="test",
        parameters={},
        handler=mock_dangerous,
        dangerous=True
    ))
    
    from jarvis.tools.dispatcher import ToolCall
    from jarvis.core.confirm import VoiceConfirm
    from unittest.mock import MagicMock
    
    # Устанавливаем мок VoiceConfirm
    mock_vc = MagicMock(spec=VoiceConfirm)
    mock_vc.ask.return_value = False  # Пользователь запретил
    
    import jarvis.core.confirm as confirm_mod
    confirm_mod.set_voice_confirm(mock_vc)
    
    res = dispatcher.execute(ToolCall(tool="boom", params={}))
    assert res == "Действие отменено пользователем."
    mock_vc.ask.assert_called_once()
    
    # Теперь разрешаем
    mock_vc.ask.return_value = True
    res2 = dispatcher.execute(ToolCall(tool="boom", params={}))
    assert res2 == "boom"
