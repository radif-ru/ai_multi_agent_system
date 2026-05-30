"""Тесты для UserRepository (SQLite-backed)."""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from app.core.events import EventBus, UserCreated
from app.users.repository import UserRepository


@pytest_asyncio.fixture
async def repo(tmp_path: Path):
    r = UserRepository(db_path=tmp_path / "memory.db")
    await r.init()
    try:
        yield r
    finally:
        await r.close()


async def test_get_or_create_creates_new_user(repo: UserRepository) -> None:
    user, created = await repo.get_or_create("telegram", "123456", "Test User")

    assert created is True
    assert user.id == 1
    assert user.channel == "telegram"
    assert user.external_id == "123456"
    assert user.display_name == "Test User"
    assert user.created_at is not None


async def test_get_or_create_returns_existing_user(repo: UserRepository) -> None:
    user1, created1 = await repo.get_or_create("console", "alice")
    user2, created2 = await repo.get_or_create("console", "alice")

    assert created1 is True
    assert created2 is False
    assert user1.id == user2.id
    assert user1.channel == user2.channel
    assert user1.external_id == user2.external_id


async def test_get_by_external_finds_created_user(repo: UserRepository) -> None:
    await repo.get_or_create("telegram", "789", "Bob")

    user = await repo.get_by_external("telegram", "789")

    assert user is not None
    assert user.id == 1
    assert user.channel == "telegram"
    assert user.external_id == "789"


async def test_get_by_external_returns_none_for_nonexistent(
    repo: UserRepository,
) -> None:
    user = await repo.get_by_external("telegram", "999999")
    assert user is None


async def test_get_returns_user_by_id(repo: UserRepository) -> None:
    created_user, _ = await repo.get_or_create("console", "charlie")

    user = await repo.get(created_user.id)

    assert user is not None
    assert user.id == created_user.id
    assert user.channel == "console"


async def test_get_returns_none_for_nonexistent_id(repo: UserRepository) -> None:
    user = await repo.get(999)
    assert user is None


async def test_different_channels_separate_users(repo: UserRepository) -> None:
    user1, _ = await repo.get_or_create("telegram", "123")
    user2, _ = await repo.get_or_create("console", "123")

    assert user1.id != user2.id
    assert user1.channel == "telegram"
    assert user2.channel == "console"


async def test_auto_increment_ids(repo: UserRepository) -> None:
    user1, _ = await repo.get_or_create("telegram", "1")
    user2, _ = await repo.get_or_create("telegram", "2")
    user3, _ = await repo.get_or_create("telegram", "3")

    assert user1.id == 1
    assert user2.id == 2
    assert user3.id == 3


async def test_user_persists_across_restart(tmp_path: Path) -> None:
    """После рестарта репозитория get_or_create возвращает тот же user.id."""
    db = tmp_path / "memory.db"

    repo1 = UserRepository(db_path=db)
    await repo1.init()
    user1, created1 = await repo1.get_or_create("telegram", "42", "Alice")
    assert created1 is True
    await repo1.close()

    repo2 = UserRepository(db_path=db)
    await repo2.init()
    try:
        user2, created2 = await repo2.get_or_create("telegram", "42")
        assert created2 is False
        assert user2.id == user1.id
        assert user2.display_name == "Alice"
    finally:
        await repo2.close()


async def test_user_created_published_only_on_first_insert(tmp_path: Path) -> None:
    """`UserCreated` публикуется ровно один раз перез все рестарты."""
    db = tmp_path / "memory.db"
    bus = EventBus()
    events: list[UserCreated] = []

    async def capture(ev: UserCreated) -> None:
        events.append(ev)

    bus.subscribe(UserCreated, capture)

    repo1 = UserRepository(db_path=db, event_bus=bus)
    await repo1.init()
    await repo1.get_or_create("console", "bob")
    await repo1.get_or_create("console", "bob")  # не должно двоить
    await repo1.close()

    repo2 = UserRepository(db_path=db, event_bus=bus)
    await repo2.init()
    await repo2.get_or_create("console", "bob")  # существует — события нет
    await repo2.close()

    assert len(events) == 1
    assert events[0].user.external_id == "bob"
