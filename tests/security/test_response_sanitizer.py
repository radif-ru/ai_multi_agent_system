"""Тесты для ResponseSanitizer.

См. задачу 7.1 спринта 05.
"""

import pytest

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


@pytest.mark.parametrize(
    "text,mask",
    [
        # 1. Windows-путь с пробелами.
        ("Открой D:\\My Documents\\report.txt", "[FILE_PATH]"),
        # 2. Windows-путь в нижнем регистре диска.
        ("См. c:\\temp\\foo.log", "[FILE_PATH]"),
        # 3. Unix-путь — глубокая вложенность.
        ("Лог: /var/log/app/agent.log", "[FILE_PATH]"),
        # 4. ENV-ключ с кавычками.
        ('TELEGRAM_BOT_TOKEN="123:abcDEF"', "[CONFIG_KEY]"),
        # 5. Dot-конфиг.
        ("Поправь sentry.dsn=https://...", "[CONFIG_KEY]"),
        # 6. System-section в нижнем регистре.
        ("# запреты — нельзя то-то", "[SYSTEM_SECTION]"),
        # 7. Идентичность через 'есть'.
        ("Ты есть AI-помощник по имени Cascade", "[SYSTEM_IDENTITY]"),
        # 8. Идентичность через тире.
        ("Ты — агент-исполнитель", "[SYSTEM_IDENTITY]"),
    ],
)
def test_sanitize_response_bypass_patterns(text, mask):
    """Bypass-кейсы (спринт 08, задача 1.2): чувствительная информация маскируется."""
    result = sanitize_response(text)
    assert mask in result, f"маска {mask!r} не появилась для: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        # Tilde-путь без двух слешей — known limitation: regex требует два '/'.
        "Конфиг лежит в ~/file.txt",
        # Относительный путь без начального '/' — known limitation.
        "См. app/config.py",
    ],
)
def test_sanitize_response_known_limitations(text):
    """Known limitations: эти кейсы НЕ маскируются (см. security.md §5)."""
    result = sanitize_response(text)
    assert "[FILE_PATH]" not in result, (
        f"кейс неожиданно замаскирован — обнови security.md §5: {text!r}"
    )
