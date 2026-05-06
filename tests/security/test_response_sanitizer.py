"""Тесты для ResponseSanitizer.

См. задачу 7.1 спринта 05.
"""

from app.security.response_sanitizer import sanitize_response


def test_sanitize_response_normal_text():
    """Нормальный текст не изменяется."""
    text = "Привет, как дела? Вот ответ на твой вопрос."
    result = sanitize_response(text)
    assert result == text


def test_sanitize_response_windows_path():
    """Пути Windows маскируются."""
    text = "Файл находится по пути C:\\Users\\username\\Documents\\file.txt"
    result = sanitize_response(text)
    assert "[FILE_PATH]" in result
    assert "C:\\Users\\username\\Documents\\file.txt" not in result


def test_sanitize_response_unix_path():
    """Пути Unix маскируются."""
    text = "Файл находится по пути /home/user/documents/file.txt"
    result = sanitize_response(text)
    assert "[FILE_PATH]" in result
    assert "/home/user/documents/file.txt" not in result


def test_sanitize_response_config_key_env():
    """Конфигурационные ключи в формате ENV маскируются."""
    text = "Переменная DATABASE_URL=postgresql://localhost/db"
    result = sanitize_response(text)
    assert "[CONFIG_KEY]" in result
    assert "DATABASE_URL=postgresql://localhost/db" not in result


def test_sanitize_response_config_key_dot():
    """Конфигурационные ключи в формате config.key маскируются."""
    text = "Настройка ollama.default_model=qwen3.5:4b"
    result = sanitize_response(text)
    assert "[CONFIG_KEY]" in result
    assert "ollama.default_model=qwen3.5:4b" not in result


def test_sanitize_response_system_section():
    """Фрагменты системного промпта с секциями маскируются."""
    text = "# Запреты (важно)\nНельзя делать плохие вещи"
    result = sanitize_response(text)
    assert "[SYSTEM_SECTION]" in result
    assert "# Запреты" not in result


def test_sanitize_response_system_identity():
    """Фрагменты системного промпта с идентичностью маскируются."""
    text = "Ты — AI-агент, который помогает пользователям"
    result = sanitize_response(text)
    assert "[SYSTEM_IDENTITY]" in result
    assert "Ты — AI" not in result


def test_sanitize_response_multiple_patterns():
    """Несколько паттернов маскируются одновременно."""
    text = "Файл по пути /home/user/file.txt и настройка api.key=value"
    result = sanitize_response(text)
    assert "[FILE_PATH]" in result
    assert "[CONFIG_KEY]" in result
    assert "/home/user/file.txt" not in result
    assert "api.key=value" not in result


def test_sanitize_response_empty_string():
    """Пустая строка не вызывает ошибок."""
    text = ""
    result = sanitize_response(text)
    assert result == ""


def test_sanitize_response_no_sensitive_info():
    """Текст без чувствительной информации не изменяется."""
    text = "Просто обычный текст без путей и настроек"
    result = sanitize_response(text)
    assert result == text
