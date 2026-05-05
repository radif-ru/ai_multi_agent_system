"""Тесты для UserRepository."""

import pytest

from app.users.models import User
from app.users.repository import UserRepository


@pytest.mark.asyncio
async def test_get_or_create_creates_new_user() -> None:
    """get_or_create создаёт нового пользователя при первом вызове."""
    repo = UserRepository()
    user, created = await repo.get_or_create("telegram", "123456", "Test User")

    assert created is True
    assert user.id == 1
    assert user.channel == "telegram"
    assert user.external_id == "123456"
    assert user.display_name == "Test User"
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_user() -> None:
    """Повторный get_or_create возвращает того же пользователя с created=False."""
    repo = UserRepository()

    user1, created1 = await repo.get_or_create("console", "alice")
    user2, created2 = await repo.get_or_create("console", "alice")

    assert created1 is True
    assert created2 is False
    assert user1.id == user2.id
    assert user1.channel == user2.channel
    assert user1.external_id == user2.external_id


@pytest.mark.asyncio
async def test_get_by_external_finds_created_user() -> None:
    """get_by_external находит созданного пользователя."""
    repo = UserRepository()
    await repo.get_or_create("telegram", "789", "Bob")

    user = await repo.get_by_external("telegram", "789")

    assert user is not None
    assert user.id == 1
    assert user.channel == "telegram"
    assert user.external_id == "789"


@pytest.mark.asyncio
async def test_get_by_external_returns_none_for_nonexistent() -> None:
    """get_by_external возвращает None для несуществующего пользователя."""
    repo = UserRepository()
    user = await repo.get_by_external("telegram", "999999")

    assert user is None


@pytest.mark.asyncio
async def test_get_returns_user_by_id() -> None:
    """get возвращает пользователя по внутреннему id."""
    repo = UserRepository()
    created_user, _ = await repo.get_or_create("console", "charlie")

    user = await repo.get(created_user.id)

    assert user is not None
    assert user.id == created_user.id
    assert user.channel == "console"


@pytest.mark.asyncio
async def test_get_returns_none_for_nonexistent_id() -> None:
    """get возвращает None для несуществующего id."""
    repo = UserRepository()
    user = await repo.get(999)

    assert user is None


@pytest.mark.asyncio
async def test_different_channels_separate_users() -> None:
    """Одинаковый external_id в разных каналах создаёт разных пользователей."""
    repo = UserRepository()

    user1, _ = await repo.get_or_create("telegram", "123")
    user2, _ = await repo.get_or_create("console", "123")

    assert user1.id != user2.id
    assert user1.channel == "telegram"
    assert user2.channel == "console"


@pytest.mark.asyncio
async def test_auto_increment_ids() -> None:
    """id автоинкрементируются корректно."""
    repo = UserRepository()

    user1, _ = await repo.get_or_create("telegram", "1")
    user2, _ = await repo.get_or_create("telegram", "2")
    user3, _ = await repo.get_or_create("telegram", "3")

    assert user1.id == 1
    assert user2.id == 2
    assert user3.id == 3
