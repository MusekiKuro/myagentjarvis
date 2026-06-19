from unittest.mock import MagicMock

from jarvis.core.confirm import VoiceConfirm


def test_voice_confirm_yes():
    # Мок TTS/STT
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_speak = MagicMock()

    # STT возвращает "да"
    mock_stt.transcribe.return_value = " да, конечно "

    vc = VoiceConfirm(tts=mock_tts, stt=mock_stt, speak_fn=mock_speak)

    # Подменяем record_until_silence для теста (чтобы не слушать микрофон)
    from unittest.mock import patch
    with patch("jarvis.core.listener.record_until_silence") as mock_record:
        mock_record.return_value = b"fakeaudio"
        result = vc.ask("Разрешить?")

    assert result is True
    mock_speak.assert_called_once_with("Разрешить?")
    mock_record.assert_called_once()
    mock_stt.transcribe.assert_called_once_with(b"fakeaudio")


def test_voice_confirm_no():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_speak = MagicMock()

    mock_stt.transcribe.return_value = " нет отмена "

    vc = VoiceConfirm(tts=mock_tts, stt=mock_stt, speak_fn=mock_speak)

    from unittest.mock import patch
    with patch("jarvis.core.listener.record_until_silence") as mock_record:
        mock_record.return_value = b"fakeaudio"
        result = vc.ask("Разрешить?")

    assert result is False
    # Сначала спросил "Разрешить?", потом ответил "Принято, отменяю."
    assert mock_speak.call_count == 2
    mock_speak.assert_any_call("Разрешить?")
    mock_speak.assert_any_call("Принято, отменяю.")


def test_voice_confirm_silence():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_speak = MagicMock()

    vc = VoiceConfirm(tts=mock_tts, stt=mock_stt, speak_fn=mock_speak)

    from unittest.mock import patch
    with patch("jarvis.core.listener.record_until_silence") as mock_record:
        mock_record.return_value = None  # Тишина
        result = vc.ask("Разрешить?")

    assert result is False
    assert mock_speak.call_count == 2
    mock_speak.assert_any_call("Разрешить?")
    mock_speak.assert_any_call("Принято, отменяю.")


def test_voice_confirm_retry():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_speak = MagicMock()

    # Сначала бормотание, потом "да"
    mock_stt.transcribe.side_effect = [" не понимаю ", " да "]

    vc = VoiceConfirm(tts=mock_tts, stt=mock_stt, speak_fn=mock_speak)

    from unittest.mock import patch
    with patch("jarvis.core.listener.record_until_silence") as mock_record:
        mock_record.return_value = b"fakeaudio"
        result = vc.ask("Разрешить?")

    assert result is True
    assert mock_speak.call_count == 2
    mock_speak.assert_any_call("Разрешить?")
    mock_speak.assert_any_call("Сэр, не расслышал. Да или нет?")
    assert mock_stt.transcribe.call_count == 2
