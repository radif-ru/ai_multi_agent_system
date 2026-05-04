"""Тесты утилит форматирования Telegram-адаптера."""

from __future__ import annotations

from aiogram.enums import ParseMode

from app.adapters.telegram.utils import format_for_telegram


def test_format_for_telegram_plain_text():
    """Обычный текст без кода возвращает None."""
    text = "Привет, как дела?"
    formatted, parse_mode = format_for_telegram(text)
    assert formatted == text
    assert parse_mode is None


def test_format_for_telegram_markdown_text():
    """Текст с markdown возвращает MARKDOWN."""
    text = "Привет, *как дела*?"
    formatted, parse_mode = format_for_telegram(text)
    assert formatted == text
    assert parse_mode == ParseMode.MARKDOWN


def test_format_for_telegram_code_block():
    """Блок кода преобразуется в HTML."""
    text = "```python\nprint('hello')\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert '<pre><code class="language-python">' in formatted
    assert "print(&#x27;hello&#x27;)" in formatted  # Экранированные кавычки
    assert "</code></pre>" in formatted


def test_format_for_telegram_code_block_with_language():
    """Блок кода с языком сохраняет язык в class."""
    text = "```javascript\nconsole.log('hello');\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert '<pre><code class="language-javascript">' in formatted
    assert "console.log(&#x27;hello&#x27;);" in formatted  # Экранированные кавычки


def test_format_for_telegram_code_block_no_language():
    """Блок кода без языка получает class='language-text'."""
    text = "```\nprint('hello')\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert '<pre><code class="language-text">' in formatted


def test_format_for_telegram_multiple_code_blocks():
    """Несколько блоков кода преобразуются все."""
    text = "```python\na = 1\n```\n\nТекст между\n\n```bash\necho hello\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert '<pre><code class="language-python">' in formatted
    assert '<pre><code class="language-bash">' in formatted


def test_format_for_telegram_code_with_special_chars():
    """Специальные символы в коде экранируются."""
    text = "```python\nprint('<script>')\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert "&lt;script&gt;" in formatted


def test_format_for_telegram_code_with_ampersand():
    """Амперсанд в коде экранируется."""
    text = "```python\na & b\n```"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert "&amp;" in formatted


def test_format_for_telegram_text_around_code():
    """Текст вокруг кодовых блоков экранируется."""
    text = "Привет, вот код:\n```python\nprint('hello')\n```\nИ ещё текст"
    formatted, parse_mode = format_for_telegram(text)
    assert parse_mode == ParseMode.HTML
    assert "&lt;pre&gt;" not in formatted  # Наши теги не экранированы
    assert "Привет, вот код:" in formatted
    assert "И ещё текст" in formatted
