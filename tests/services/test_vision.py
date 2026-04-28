"""Тесты сервиса описания изображений.

См. задачу 3.5 спринта 02.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.vision import Vision


@pytest.fixture
def mock_ollama():
    """Мок OllamaClient."""
    from unittest.mock import MagicMock

    ollama = MagicMock()
    ollama.chat.return_value = {"message": {"content": "На фото кот"}}
    return ollama


def test_vision_describe(mock_ollama, tmp_path: Path) -> None:
    """Описание изображения."""
    # Создаём тестовое изображение
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake image data")

    vision = Vision(ollama=mock_ollama, model="llava:13b")
    result = vision.describe(test_image, caption="Мой кот")

    assert result == "На фото кот"
    mock_ollama.chat.assert_called_once()
    call_kwargs = mock_ollama.chat.call_args.kwargs
    assert call_kwargs["model"] == "llava:13b"
    assert "images" in call_kwargs
    assert len(call_kwargs["images"]) == 1
    assert call_kwargs["messages"][0]["content"] == "Опиши, что изображено на этой картинке. Caption: Мой кот"


def test_vision_describe_no_caption(mock_ollama, tmp_path: Path) -> None:
    """Описание изображения без caption."""
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake image data")

    vision = Vision(ollama=mock_ollama, model="llava:13b")
    result = vision.describe(test_image)

    assert result == "На фото кот"
    call_kwargs = mock_ollama.chat.call_args.kwargs
    assert "Caption:" not in call_kwargs["messages"][0]["content"]


def test_vision_describe_file_error(mock_ollama, tmp_path: Path) -> None:
    """Ошибка чтения файла."""
    test_image = tmp_path / "nonexistent.jpg"

    vision = Vision(ollama=mock_ollama, model="llava:13b")
    with pytest.raises(Exception):
        vision.describe(test_image)


def test_vision_describe_llm_error(mock_ollama, tmp_path: Path) -> None:
    """Ошибка LLM."""
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake image data")

    mock_ollama.chat.side_effect = Exception("LLM error")

    vision = Vision(ollama=mock_ollama, model="llava:13b")
    with pytest.raises(Exception):
        vision.describe(test_image)
