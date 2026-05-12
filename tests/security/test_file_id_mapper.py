"""Тесты `FileIdMapper`.

Источник истины маппингов после задачи 06.3-bis.3 — таблица `dialog_journal`
в `data/memory.db`. Тесты используют реальный `DialogJournal` для записи
строк и проверяют, что `FileIdMapper.init()`/`get_path()` корректно
поднимают и читают `(file_id, file_path)`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.security.file_id_mapper import FileIdMapper
from app.services.dialog_journal import DialogJournal


async def _seed_journal(
    db_path: Path,
    *,
    file_id: str,
    file_path: Path,
    user_id: int = 1,
    archived: bool = False,
) -> DialogJournal:
    journal = DialogJournal(db_path=db_path)
    await journal.init()
    await journal.append(
        user_id=user_id,
        chat_id=10,
        conversation_id="c1",
        role="user",
        kind="document",
        content="goal",
        file_id=file_id,
        file_path=str(file_path),
        message_id=42,
    )
    if archived:
        await journal.mark_archived(user_id=user_id, conversation_id="c1")
    return journal


def test_generate_id_creates_unique_id(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    file_id = mapper.generate_id(tmp_path / "a.txt")
    assert file_id.startswith("file_")
    assert len(file_id) == len("file_") + 24
    mapper.close()


def test_generate_id_same_path_returns_same_id(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    path = tmp_path / "a.txt"
    assert mapper.generate_id(path) == mapper.generate_id(path)
    mapper.close()


def test_generate_id_different_paths_create_different_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    id1 = mapper.generate_id(tmp_path / "a.txt")
    id2 = mapper.generate_id(tmp_path / "b.txt")
    assert id1 != id2
    mapper.close()


def test_get_path_returns_correct_path(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    target = tmp_path / "a.txt"
    fid = mapper.generate_id(target)
    assert mapper.get_path(fid) == target
    mapper.close()


def test_get_path_unknown_id_returns_none(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    assert mapper.get_path("file_unknown") is None
    mapper.close()


def test_clear_clears_in_memory_mappings(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    path = tmp_path / "a.txt"
    fid = mapper.generate_id(path)
    assert mapper.get_path(fid) == path
    mapper.clear()
    # Запись в журнал делает подписчик — здесь её нет, поэтому после clear
    # путь не восстанавливается.
    assert mapper.get_path(fid) is None
    mapper.close()


@pytest.mark.asyncio
async def test_init_loads_mappings_from_dialog_journal(tmp_path: Path) -> None:
    """`init()` подтягивает `(file_id, file_path)` из `dialog_journal`."""
    db_path = tmp_path / "memory.db"
    test_file = tmp_path / "doc.txt"
    test_file.write_text("data", encoding="utf-8")

    journal = await _seed_journal(db_path, file_id="file_abc", file_path=test_file)
    await journal.close()

    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    assert mapper.get_path("file_abc") == test_file
    mapper.close()


@pytest.mark.asyncio
async def test_init_skips_missing_files(tmp_path: Path) -> None:
    """Если файла больше нет на диске — маппинг не подтягивается в кеш."""
    db_path = tmp_path / "memory.db"
    missing = tmp_path / "ghost.txt"  # не создаём
    journal = await _seed_journal(db_path, file_id="file_ghost", file_path=missing)
    await journal.close()

    mapper = FileIdMapper(db_path=db_path)
    mapper.init()
    assert mapper.get_path("file_ghost") is None
    mapper.close()


@pytest.mark.asyncio
async def test_get_path_reads_from_journal_when_not_in_memory(tmp_path: Path) -> None:
    """Если ID нет в кеше, `get_path` читает из `dialog_journal`."""
    db_path = tmp_path / "memory.db"
    test_file = tmp_path / "later.txt"
    test_file.write_text("x", encoding="utf-8")

    mapper = FileIdMapper(db_path=db_path)
    # Сначала открываем mapper, потом досыпаем запись в журнал — имитация
    # ситуации, когда подписчик пишет уже после старта.
    journal = DialogJournal(db_path=db_path)
    await journal.init()
    mapper.init()  # init после создания таблицы
    await journal.append(
        user_id=1,
        chat_id=10,
        conversation_id="c1",
        role="user",
        kind="document",
        content="goal",
        file_id="file_late",
        file_path=str(test_file),
    )
    await journal.close()

    # В памяти маппинга нет — но он есть в БД.
    assert mapper.get_path("file_late") == test_file
    mapper.close()


def test_init_tolerates_missing_dialog_journal_table(tmp_path: Path) -> None:
    """Если таблица ещё не создана — init не падает, кеш пуст."""
    db_path = tmp_path / "memory.db"
    db_path.touch()
    mapper = FileIdMapper(db_path=db_path)
    mapper.init()  # не должен бросать
    assert mapper.get_path("file_anything") is None
    mapper.close()
