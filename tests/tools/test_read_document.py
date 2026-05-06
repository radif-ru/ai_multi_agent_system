"""Тесты tool `read_document`.

См. задачу 3.2 спринта 02.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.security import clear_global_mapper, get_global_mapper
from app.tools.read_document import ReadDocumentTool
from app.tools.errors import ToolError


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Временная директория для тестов."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    return tmp


@pytest.fixture
def tool(tmp_dir: Path) -> ReadDocumentTool:
    """Экземпляр tool для тестов."""
    return ReadDocumentTool(
        tmp_files_dir=tmp_dir,
        max_document_chars=50000,
        max_images=20,
        ocr_enabled=False,
        ocr_min_text_threshold=100,
    )


@pytest.mark.asyncio
async def test_read_txt_file(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Чтение TXT-файла."""
    test_file = tmp_dir / "test.txt"
    test_file.write_text("Hello, world!", encoding="utf-8")

    result = await tool.run({"path": str(test_file)}, MagicMock())

    assert "Hello, world!" in result


@pytest.mark.asyncio
async def test_read_md_file(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Чтение MD-файла."""
    test_file = tmp_dir / "test.md"
    test_file.write_text("# Header\n\nContent", encoding="utf-8")

    result = await tool.run({"path": str(test_file)}, MagicMock())

    assert "# Header" in result
    assert "Content" in result


@pytest.mark.asyncio
async def test_read_pdf_file(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Чтение PDF-файла."""
    try:
        from pypdf import PdfWriter
    except ImportError:
        pytest.skip("pypdf not installed")

    test_file = tmp_dir / "test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with test_file.open("wb") as f:
        writer.write(f)

    # PDF без текста - должно вернуть пустую строку или не упасть
    result = await tool.run({"path": str(test_file)}, MagicMock())
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_max_chars_truncation(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Усечение при превышении max_chars."""
    test_file = tmp_dir / "test.txt"
    long_text = "A" * 10000
    test_file.write_text(long_text, encoding="utf-8")

    result = await tool.run({"path": str(test_file), "max_chars": 100}, MagicMock())

    assert len(result) <= 100 + len("... [truncated]")
    assert "... [truncated]" in result


@pytest.mark.asyncio
async def test_path_traversal_protection(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Защита от path traversal."""
    # Попытка выйти за пределы tmp_dir через ..
    malicious_path = str(tmp_dir / ".." / "etc" / "passwd")

    with pytest.raises(ToolError, match="путь вне разрешённой"):
        await tool.run({"path": malicious_path}, MagicMock())


@pytest.mark.asyncio
async def test_path_outside_tmp_dir(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Отклонение пути вне tmp_files_dir."""
    # Файл вне tmp_dir
    other_file = tmp_dir.parent / "outside.txt"
    other_file.write_text("secret", encoding="utf-8")

    with pytest.raises(ToolError, match="путь вне разрешённой"):
        await tool.run({"path": str(other_file)}, MagicMock())


@pytest.mark.asyncio
async def test_unsupported_file_type(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Неизвестное расширение файла."""
    test_file = tmp_dir / "test.xyz"
    test_file.write_text("content", encoding="utf-8")

    with pytest.raises(ToolError, match="неподдерживаемый тип"):
        await tool.run({"path": str(test_file)}, MagicMock())


@pytest.mark.asyncio
async def test_file_not_found(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Файл не существует."""
    nonexistent = tmp_dir / "nonexistent.txt"
    with pytest.raises(ToolError, match="файл не найден"):
        await tool.run({"path": str(nonexistent)}, MagicMock())


@pytest.mark.asyncio
async def test_not_a_file(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Путь указывает на директорию, не на файл."""
    with pytest.raises(ToolError, match="не является обычным файлом"):
        await tool.run({"path": str(tmp_dir)}, MagicMock())


@pytest.mark.asyncio
async def test_file_id_reads_txt_file(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Чтение TXT-файла через file_id."""
    clear_global_mapper()
    test_file = tmp_dir / "test.txt"
    test_file.write_text("Hello, world!", encoding="utf-8")

    mapper = get_global_mapper()
    file_id = mapper.generate_id(test_file)

    result = await tool.run({"file_id": file_id}, MagicMock())

    assert "Hello, world!" in result
    clear_global_mapper()


@pytest.mark.asyncio
async def test_file_id_not_found_error(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Ошибка при неизвестном file_id."""
    clear_global_mapper()
    with pytest.raises(ToolError, match="file_id .* не найден"):
        await tool.run({"file_id": "file_unknown"}, MagicMock())
    clear_global_mapper()


@pytest.mark.asyncio
async def test_requires_path_or_file_id(tool: ReadDocumentTool, tmp_dir: Path) -> None:
    """Ошибка при отсутствии path и file_id."""
    clear_global_mapper()
    with pytest.raises(ToolError, match="требуется path или file_id"):
        await tool.run({}, MagicMock())
    clear_global_mapper()
