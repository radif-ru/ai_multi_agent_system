"""Тесты app.services.tmp_cleanup."""

from datetime import datetime
from pathlib import Path

import pytest

from app.core.events import ConversationArchived, EventBus
from app.services.tmp_cleanup import _cleanup_tmp_images, on_conversation_archived_cleanup
from app.users.models import User


@pytest.fixture
def tmp_dir(tmp_path):
    """Временная директория для тестов."""
    return tmp_path / "tmp"


@pytest.fixture
def user():
    return User(
        id=1,
        channel="telegram",
        external_id="12345",
        display_name="Test User",
        created_at=datetime.now(),
    )


def test_cleanup_tmp_images_deletes_old_files(tmp_dir):
    """Удаляет изображения старше 1 часа."""
    import os
    import time

    # Создаём старый файл (старше 1 часа)
    old_file = tmp_dir / "old.jpg"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text("old image")
    # Устанавливаем время модификации 2 часа назад
    old_mtime = time.time() - 7200
    os.utime(old_file, (old_mtime, old_mtime))

    # Создаём новый файл (моложе 1 часа)
    new_file = tmp_dir / "new.jpg"
    new_file.write_text("new image")

    deleted = _cleanup_tmp_images(tmp_dir)

    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_tmp_images_skips_recent_files(tmp_dir):
    """Не удаляет изображения моложе 1 часа."""
    # Создаём новый файл
    new_file = tmp_dir / "new.jpg"
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text("new image")

    deleted = _cleanup_tmp_images(tmp_dir)

    assert deleted == 0
    assert new_file.exists()


def test_cleanup_tmp_images_skips_non_image_files(tmp_dir):
    """Не удаляет не-изображения."""
    import os
    import time

    # Создаём старый текстовый файл
    old_txt = tmp_dir / "old.txt"
    old_txt.parent.mkdir(parents=True, exist_ok=True)
    old_txt.write_text("old text")
    # Устанавливаем время модификации 2 часа назад
    old_mtime = time.time() - 7200
    os.utime(old_txt, (old_mtime, old_mtime))

    deleted = _cleanup_tmp_images(tmp_dir)

    assert deleted == 0
    assert old_txt.exists()


def test_cleanup_tmp_images_handles_nonexistent_dir(tmp_dir):
    """Не падает если директория не существует."""
    deleted = _cleanup_tmp_images(tmp_dir)

    assert deleted == 0


async def test_on_conversation_archived_cleanup_calls_cleanup(tmp_dir, user):
    """Подписчик вызывает cleanup при получении события."""
    # Создаём старый файл
    import os
    import time

    old_file = tmp_dir / "old.jpg"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text("old image")
    old_mtime = time.time() - 7200
    os.utime(old_file, (old_mtime, old_mtime))

    event = ConversationArchived(
        user=user,
        conversation_id="conv123",
        chunks=5,
        channel="telegram",
    )

    await on_conversation_archived_cleanup(event, tmp_dir=tmp_dir)

    assert not old_file.exists()


async def test_on_conversation_archived_cleanup_handles_errors(tmp_dir, user):
    """Подписчик не падает при ошибке в cleanup."""
    from unittest.mock import patch

    event = ConversationArchived(
        user=user,
        conversation_id="conv123",
        chunks=5,
        channel="telegram",
    )

    # Симулируем ошибку в _cleanup_tmp_images
    with patch("app.services.tmp_cleanup._cleanup_tmp_images", side_effect=RuntimeError("test error")):
        # Подписчик не должен падать
        await on_conversation_archived_cleanup(event, tmp_dir=tmp_dir)
