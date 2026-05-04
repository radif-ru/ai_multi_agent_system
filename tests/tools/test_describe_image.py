"""Тесты tool `describe_image`.

См. задачу 1.5 спринта 03.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.describe_image import DescribeImageTool
from app.tools.errors import ToolError


class _FakeLLM:
    """Фейковый LLM для тестов."""

    async def chat(self, *, model: str, messages: list[dict]) -> str:
        return "Описание изображения: кот на диване"


class _FakeSettings:
    vision_model: str = "gemma3:4b"


@pytest.fixture
def ctx() -> SimpleNamespace:
    return SimpleNamespace()


async def test_describe_image_valid_path(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool описывает изображение по валидному пути."""
    # Создаём тестовое изображение
    image_file = tmp_path / "test.jpg"
    image_file.write_bytes(b"fake image data")

    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = _FakeLLM()
    ctx.semantic_memory = None
    ctx.skills = None

    result = await tool.run({"image_path": str(image_file)}, ctx)
    # Результат должен содержать описание
    assert "кот" in result or "Описание" in result


async def test_describe_image_not_in_tmp(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool отклоняет путь вне tmp/."""
    # Создаём директорию sibling к tmp_path
    parent = tmp_path.parent
    other_dir = parent / "other"
    other_dir.mkdir(exist_ok=True)
    image_file = other_dir / "test.jpg"
    image_file.write_bytes(b"fake image data")

    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = None
    ctx.semantic_memory = None
    ctx.skills = None

    with pytest.raises(ToolError, match="path not allowed"):
        await tool.run({"image_path": str(image_file)}, ctx)


async def test_describe_image_path_traversal(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool отклоняет пути с .. traversal."""
    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = None
    ctx.semantic_memory = None
    ctx.skills = None

    with pytest.raises(ToolError, match="path not allowed"):
        await tool.run({"image_path": "../etc/passwd"}, ctx)


async def test_describe_image_file_not_found(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool возвращает ошибку для несуществующего файла."""
    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = None
    ctx.semantic_memory = None
    ctx.skills = None

    with pytest.raises(ToolError, match="file not found"):
        await tool.run({"image_path": str(tmp_path / "nonexistent.jpg")}, ctx)


async def test_describe_image_not_an_image(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool отклоняет не-изображения по расширению."""
    text_file = tmp_path / "test.txt"
    text_file.write_text("not an image")

    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = None
    ctx.semantic_memory = None
    ctx.skills = None

    with pytest.raises(ToolError, match="not an image file"):
        await tool.run({"image_path": str(text_file)}, ctx)


async def test_describe_image_with_caption(tmp_path: Path, ctx: SimpleNamespace) -> None:
    """Tool передаёт caption в Vision."""
    image_file = tmp_path / "test.jpg"
    image_file.write_bytes(b"fake image data")

    tool = DescribeImageTool(tmp_dir=str(tmp_path))
    ctx.user_id = 1
    ctx.chat_id = 1
    ctx.conversation_id = "test"
    ctx.settings = _FakeSettings()
    ctx.llm = _FakeLLM()
    ctx.semantic_memory = None
    ctx.skills = None

    result = await tool.run({"image_path": str(image_file), "caption": "Мой кот"}, ctx)
    # Caption должен быть передан в Vision (проверяем что не падает)
    assert result
