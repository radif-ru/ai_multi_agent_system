"""Тесты для FileIdMapper."""

from pathlib import Path

import pytest

from app.security.file_id_mapper import (
    FileIdMapper,
    clear_global_mapper,
    get_global_mapper,
)


def test_generate_id_creates_unique_id():
    """Генерация ID создаёт уникальный идентификатор."""
    mapper = FileIdMapper()
    path = Path("/tmp/test.txt")

    file_id = mapper.generate_id(path)

    assert file_id.startswith("file_")
    assert len(file_id) == len("file_") + 24  # 12 hex bytes = 24 chars


def test_generate_id_same_path_returns_same_id():
    """Повторный вызов для того же пути возвращает тот же ID."""
    mapper = FileIdMapper()
    path = Path("/tmp/test.txt")

    file_id1 = mapper.generate_id(path)
    file_id2 = mapper.generate_id(path)

    assert file_id1 == file_id2


def test_generate_id_different_paths_create_different_ids():
    """Разные пути создают разные ID."""
    mapper = FileIdMapper()
    path1 = Path("/tmp/test1.txt")
    path2 = Path("/tmp/test2.txt")

    file_id1 = mapper.generate_id(path1)
    file_id2 = mapper.generate_id(path2)

    assert file_id1 != file_id2


def test_get_path_returns_correct_path():
    """Восстановление пути по ID возвращает правильный путь."""
    mapper = FileIdMapper()
    path = Path("/tmp/test.txt")

    file_id = mapper.generate_id(path)
    recovered_path = mapper.get_path(file_id)

    assert recovered_path == path


def test_get_path_unknown_id_returns_none():
    """Запрос неизвестного ID возвращает None."""
    mapper = FileIdMapper()

    recovered_path = mapper.get_path("file_unknown")

    assert recovered_path is None


def test_clear_clears_mappings():
    """Метод clear очищает все маппинги."""
    mapper = FileIdMapper()
    path = Path("/tmp/test.txt")

    file_id = mapper.generate_id(path)
    assert mapper.get_path(file_id) == path

    mapper.clear()
    assert mapper.get_path(file_id) is None


def test_generate_id_after_clear_creates_new_id():
    """После clear генерация создаёт новые ID."""
    mapper = FileIdMapper()
    path = Path("/tmp/test.txt")

    file_id1 = mapper.generate_id(path)
    mapper.clear()
    file_id2 = mapper.generate_id(path)

    # ID должны быть разными, так как хранилище очищено
    assert file_id1 != file_id2


def test_get_global_mapper_returns_same_instance():
    """Глобальный маппер возвращает один и тот же экземпляр."""
    mapper1 = get_global_mapper()
    mapper2 = get_global_mapper()

    assert mapper1 is mapper2


def test_clear_global_mapper_clears_instance():
    """Очистка глобального маппера сбрасывает состояние."""
    mapper = get_global_mapper()
    path = Path("/tmp/test.txt")

    file_id = mapper.generate_id(path)
    assert mapper.get_path(file_id) == path

    clear_global_mapper()

    # После очистки создаётся новый экземпляр
    new_mapper = get_global_mapper()
    assert new_mapper is not mapper
    assert new_mapper.get_path(file_id) is None


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
