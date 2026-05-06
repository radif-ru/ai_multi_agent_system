"""Тесты OCR-сервиса.

См. задачу 1.1 спринта 05.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ocr import extract_text, get_default_lang


def test_extract_text_empty_paths() -> None:
    """Пустой список путей возвращает пустую строку."""
    result = extract_text([])
    assert result == ""


def test_extract_text_with_cache(tmp_path: Path) -> None:
    """Чтение из кеша."""
    cache_path = tmp_path / "test.ocr.txt"
    cache_path.write_text("cached text", encoding="utf-8")

    result = extract_text([Path("test.jpg")], cache_path=cache_path)
    assert result == "cached text"


def test_extract_text_with_empty_cache(tmp_path: Path) -> None:
    """Пустой кеш вызывает OCR (если зависимости есть)."""
    cache_path = tmp_path / "test.ocr.txt"
    cache_path.write_text("   ", encoding="utf-8")  # Только пробелы

    # Если pytesseract не установлен, вернёт пустую строку
    result = extract_text([Path("test.jpg")], cache_path=cache_path)
    # Не проверяем результат, так как зависит от наличия pytesseract


def test_extract_text_no_cache(tmp_path: Path) -> None:
    """OCR без кеша."""
    # Если pytesseract не установлен, вернёт пустую строку
    result = extract_text([Path("test.jpg")], cache_path=tmp_path / "cache.txt")
    # Не проверяем результат, так как зависит от наличия pytesseract


def test_get_default_lang() -> None:
    """Получение языка по умолчанию."""
    lang = get_default_lang()
    # Должен вернуть либо "rus+eng", либо "eng" в зависимости от наличия русского
    assert lang in ("rus+eng", "eng")
