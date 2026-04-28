"""Тесты `app.utils.text.split_long_message`."""

from __future__ import annotations

import pytest

from app.utils.text import split_long_message


def test_short_text_returned_as_single_part() -> None:
    assert split_long_message("hello", 10) == ["hello"]


def test_text_equal_to_limit_not_split() -> None:
    assert split_long_message("a" * 10, 10) == ["a" * 10]


def test_long_text_split_by_limit() -> None:
    text = "a" * 10 + "b" * 10 + "c" * 5
    parts = split_long_message(text, 10)
    assert parts == ["a" * 10, "b" * 10, "c" * 5]
    assert "".join(parts) == text


def test_empty_text_returned_as_single_empty_part() -> None:
    assert split_long_message("", 10) == [""]


def test_non_positive_limit_raises() -> None:
    with pytest.raises(ValueError):
        split_long_message("abc", 0)
    with pytest.raises(ValueError):
        split_long_message("abc", -1)
