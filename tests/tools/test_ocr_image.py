"""Тесты tool `ocr_image`.

См. задачу 2.1 спринта 05.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.tools.ocr_image import OcrImageTool
from app.tools.errors import ToolError


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Временная директория для тестов."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    return tmp


@pytest.fixture
def tool(tmp_dir: Path) -> OcrImageTool:
    """Экземпляр tool для тестов."""
    return OcrImageTool(tmp_dir=tmp_dir, max_output_chars=8000)


@pytest.mark.asyncio
async def test_ocr_image_success(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Чтение из кеша OCR."""
    test_file = tmp_dir / "test.jpg"
    test_file.write_bytes(b"fake image")

    # Создаём кеш
    cache_file = tmp_dir / "test.ocr.txt"
    cache_file.write_text("recognized text", encoding="utf-8")

    result = await tool.run({"image_path": str(test_file)}, MagicMock())

    assert "recognized text" in result


@pytest.mark.asyncio
async def test_ocr_image_empty_result(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Пустой результат OCR."""
    test_file = tmp_dir / "test.jpg"
    test_file.write_bytes(b"fake image")

    result = await tool.run({"image_path": str(test_file)}, MagicMock())

    assert result == "OCR не нашёл текста на изображении"


@pytest.mark.asyncio
async def test_ocr_image_path_traversal(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Защита от path traversal."""
    malicious_path = str(tmp_dir / ".." / "etc" / "passwd")

    with pytest.raises(ToolError, match="путь вне разрешённой"):
        await tool.run({"image_path": malicious_path}, MagicMock())


@pytest.mark.asyncio
async def test_ocr_image_outside_tmp(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Отклонение пути вне tmp_dir."""
    other_file = tmp_dir.parent / "outside.jpg"
    other_file.write_bytes(b"fake image")

    with pytest.raises(ToolError, match="путь вне разрешённой"):
        await tool.run({"image_path": str(other_file)}, MagicMock())


@pytest.mark.asyncio
async def test_ocr_image_file_not_found(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Файл не существует."""
    nonexistent = tmp_dir / "nonexistent.jpg"

    with pytest.raises(ToolError, match="файл не найден"):
        await tool.run({"image_path": str(nonexistent)}, MagicMock())


@pytest.mark.asyncio
async def test_ocr_image_not_a_file(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Путь указывает на директорию."""
    with pytest.raises(ToolError, match="не является обычным файлом"):
        await tool.run({"image_path": str(tmp_dir)}, MagicMock())


@pytest.mark.asyncio
async def test_ocr_image_invalid_extension(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Неподдерживаемое расширение."""
    test_file = tmp_dir / "test.txt"
    test_file.write_text("text", encoding="utf-8")

    with pytest.raises(ToolError, match="неподдерживаемое расширение"):
        await tool.run({"image_path": str(test_file)}, MagicMock())


@pytest.mark.asyncio
async def test_ocr_image_with_lang(tool: OcrImageTool, tmp_dir: Path) -> None:
    """OCR с кастомным языком (чтение из кеша)."""
    test_file = tmp_dir / "test.jpg"
    test_file.write_bytes(b"fake image")

    # Создаём кеш
    cache_file = tmp_dir / "test.ocr.txt"
    cache_file.write_text("recognized text", encoding="utf-8")

    result = await tool.run({"image_path": str(test_file), "lang": "fra"}, MagicMock())

    assert "recognized text" in result


@pytest.mark.asyncio
async def test_ocr_image_truncation(tool: OcrImageTool, tmp_dir: Path) -> None:
    """Усечение длинного результата."""
    test_file = tmp_dir / "test.jpg"
    test_file.write_bytes(b"fake image")

    # Создаём кеш с длинным текстом
    cache_file = tmp_dir / "test.ocr.txt"
    long_text = "A" * 10000
    cache_file.write_text(long_text, encoding="utf-8")

    result = await tool.run({"image_path": str(test_file)}, MagicMock())

    assert len(result) <= 8000 + len("... [truncated]")
