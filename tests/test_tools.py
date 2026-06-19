from unittest.mock import patch

# 1. Файлы
from jarvis.tools.files import list_dir, read_file, write_file


def test_files_list_dir(tmp_path):
    # Создаем временную структуру
    d = tmp_path / "subdir"
    d.mkdir()
    f1 = tmp_path / "file1.txt"
    f1.write_text("hello")

    res = list_dir(str(tmp_path))
    assert "subdir" in res
    assert "file1.txt" in res

def test_files_read_write(tmp_path):
    f = tmp_path / "test.txt"
    res1 = write_file(str(f), "hello world")
    assert "записан" in res1

    res2 = read_file(str(f))
    assert res2 == "hello world"

# 2. Приложения
from jarvis.tools.apps import open_app, open_url


@patch("subprocess.Popen")
def test_open_app(mock_popen):
    res = open_app("notepad")
    assert "Успешно" in res or "запущено" in res
    mock_popen.assert_called_once()

@patch("webbrowser.open")
def test_open_url(mock_webbrowser):
    res = open_url("google.com")
    assert "открыта" in res
    mock_webbrowser.assert_called_once_with("https://google.com")

# 3. Система
from jarvis.tools.system import get_system_info


def test_system_info():
    # Просто проверяем, что psutil вызывается без ошибок (т.к. он установлен)
    res = get_system_info()
    assert "CPU:" in res
    assert "RAM:" in res
    assert "Диск C:\\:" in res

# 4. Поиск
from jarvis.tools.search import web_search


def test_web_search():
    # Мокаем duckduckgo_search
    with patch("duckduckgo_search.DDGS") as MockDDGS:
        mock_ddgs_instance = MockDDGS.return_value.__enter__.return_value
        mock_ddgs_instance.text.return_value = [
            {"title": "Test Title", "body": "Test Body", "href": "http://test.com"}
        ]
        res = web_search("pytest duckduckgo")
        assert "Test Title" in res
        assert "Test Body" in res
        assert "http://test.com" in res
