"""Тесты для FileIdMapper."""

from pathlib import Path
import tempfile
import sqlite3


from app.security.file_id_mapper import (
    FileIdMapper,
    clear_global_mapper,
    get_global_mapper,
)


def _init_file_contexts_db(db_path: Path) -> None:
    """Создать таблицу file_contexts для тестов."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_contexts (
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                context TEXT NOT NULL,
                file_id TEXT,
                file_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, message_id)
            )
            """
        )
        conn.commit()


def test_generate_id_creates_unique_id():
    """Генерация ID создаёт уникальный идентификатор."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path = Path("/tmp/test.txt")

        file_id = mapper.generate_id(path)

        assert file_id.startswith("file_")
        assert len(file_id) == len("file_") + 24  # 12 hex bytes = 24 chars

        mapper.close()


def test_generate_id_same_path_returns_same_id():
    """Повторный вызов для того же пути возвращает тот же ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path = Path("/tmp/test.txt")

        file_id1 = mapper.generate_id(path)
        file_id2 = mapper.generate_id(path)

        assert file_id1 == file_id2

        mapper.close()


def test_generate_id_different_paths_create_different_ids():
    """Разные пути создают разные ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path1 = Path("/tmp/test1.txt")
        path2 = Path("/tmp/test2.txt")

        file_id1 = mapper.generate_id(path1)
        file_id2 = mapper.generate_id(path2)

        assert file_id1 != file_id2

        mapper.close()


def test_get_path_returns_correct_path():
    """Восстановление пути по ID возвращает правильный путь."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path = Path("/tmp/test.txt")

        file_id = mapper.generate_id(path)
        recovered_path = mapper.get_path(file_id)

        assert recovered_path == path

        mapper.close()


def test_get_path_unknown_id_returns_none():
    """Запрос неизвестного ID возвращает None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()

        recovered_path = mapper.get_path("file_unknown")

        assert recovered_path is None

        mapper.close()


def test_clear_clears_mappings():
    """Метод clear очищает все маппинги."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path = Path("/tmp/test.txt")

        file_id = mapper.generate_id(path)
        assert mapper.get_path(file_id) == path

        mapper.clear()
        assert mapper.get_path(file_id) is None

        mapper.close()


def test_generate_id_after_clear_creates_new_id():
    """После clear генерация создаёт новые ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        mapper = FileIdMapper(db_path=db_path)
        mapper.init()
        path = Path("/tmp/test.txt")

        file_id1 = mapper.generate_id(path)
        mapper.clear()
        file_id2 = mapper.generate_id(path)

        # ID должны быть разными, так как хранилище очищено
        assert file_id1 != file_id2

        mapper.close()


def test_persistence_across_restarts():
    """Маппинги сохраняются между перезапусками (инициализация из БД)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test content")

        # Первый запуск: создаём маппинг и сохраняем в БД
        mapper1 = FileIdMapper(db_path=db_path)
        mapper1.init()
        file_id = mapper1.generate_id(test_file)
        # Сохраняем в БД через INSERT (имитация ConversationStore)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO file_contexts "
                "(user_id, message_id, file_type, context, file_id, file_path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (1, 1, "test", "test context", file_id, str(test_file)),
            )
            conn.commit()
        mapper1.close()

        # Второй запуск: маппинг должен загрузиться из БД
        mapper2 = FileIdMapper(db_path=db_path)
        mapper2.init()
        recovered_path = mapper2.get_path(file_id)
        assert recovered_path == test_file
        mapper2.close()


def test_get_path_from_db_when_not_in_memory():
    """get_path читает из БД, если маппинга нет в памяти."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        _init_file_contexts_db(db_path)
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test content")

        # Создаём маппинг и сохраняем в БД
        mapper1 = FileIdMapper(db_path=db_path)
        mapper1.init()
        file_id = mapper1.generate_id(test_file)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO file_contexts "
                "(user_id, message_id, file_type, context, file_id, file_path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (1, 1, "test", "test context", file_id, str(test_file)),
            )
            conn.commit()
        mapper1.close()

        # Новый экземпляр с пустой памятью
        mapper2 = FileIdMapper(db_path=db_path)
        mapper2.init()
        # Маппинг должен загрузиться из БД при первом запросе
        recovered_path = mapper2.get_path(file_id)
        assert recovered_path == test_file
        mapper2.close()


def test_get_global_mapper_returns_same_instance():
    """Глобальный маппер возвращает один и тот же экземпляр."""
    clear_global_mapper()  # Сбрасываем перед тестом

    mapper1 = get_global_mapper()
    mapper2 = get_global_mapper()

    assert mapper1 is mapper2

    clear_global_mapper()


def test_clear_global_mapper_clears_instance():
    """Очистка глобального маппера сбрасывает состояние."""
    clear_global_mapper()  # Сбрасываем перед тестом

    mapper = get_global_mapper()
    path = Path("/tmp/test.txt")

    file_id = mapper.generate_id(path)
    assert mapper.get_path(file_id) == path

    clear_global_mapper()

    # После очистки создаётся новый экземпляр
    new_mapper = get_global_mapper()
    assert new_mapper is not mapper
    # Маппинг из БД не должен загружаться, если файл не существует
    assert new_mapper.get_path(file_id) is None

    clear_global_mapper()


def test_global_mapper_persists_across_calls():
    """Глобальный маппер сохраняет состояние между вызовами."""
    clear_global_mapper()  # Сбрасываем перед тестом

    mapper1 = get_global_mapper()
    path = Path("/tmp/test.txt")
    file_id1 = mapper1.generate_id(path)

    mapper2 = get_global_mapper()
    recovered_path = mapper2.get_path(file_id1)

    assert recovered_path == path

    clear_global_mapper()  # Очищаем после теста
