"""Тесты сервиса транскрипции.

См. задачу 3.4 спринта 02.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.transcribe import (
    Transcriber,
    TranscriberUnavailableError,
    is_transcriber_available,
)


def test_is_transcriber_available() -> None:
    """Проверка доступности transcriber."""
    # Если faster-whisper установлен, должен вернуть True
    # В тестовой среде может быть не установлен
    result = is_transcriber_available()
    assert isinstance(result, bool)


def test_transcriber_unavailable_when_not_installed() -> None:
    """TranscriberUnavailableError когда faster-whisper не установлен."""
    # Патчим, чтобы симулировать отсутствие faster-whisper
    from app.services import transcribe
    original_model = transcribe.WhisperModel

    try:
        transcribe.WhisperModel = None
        with pytest.raises(TranscriberUnavailableError):
            Transcriber(model="base", language="ru")
    finally:
        transcribe.WhisperModel = original_model


def test_transcriber_init_with_mock() -> None:
    """Инициализация transcriber с моком WhisperModel."""
    from app.services import transcribe
    from unittest.mock import MagicMock

    original_model = transcribe.WhisperModel

    try:
        # Создаём мок WhisperModel
        mock_whisper = MagicMock()
        transcribe.WhisperModel = mock_whisper

        transcriber = Transcriber(model="base", language="ru")
        assert transcriber._model == "base"
        assert transcriber._language == "ru"
        mock_whisper.assert_called_once_with("base", device="cpu", compute_type="int8")
    finally:
        transcribe.WhisperModel = original_model


def test_transcriber_transcribe_with_mock(tmp_path: Path) -> None:
    """Транскрипция с моком WhisperModel."""
    from app.services import transcribe
    from unittest.mock import MagicMock

    original_model = transcribe.WhisperModel

    try:
        # Создаём мок WhisperModel
        mock_whisper = MagicMock()
        transcribe.WhisperModel = mock_whisper

        # Настраиваем мок
        mock_model_instance = MagicMock()
        mock_whisper.return_value = mock_model_instance

        # Создаём мок segments
        mock_segment1 = MagicMock()
        mock_segment1.text = "Привет, "
        mock_segment2 = MagicMock()
        mock_segment2.text = "мир!"

        mock_model_instance.transcribe.return_value = (
            [mock_segment1, mock_segment2],
            MagicMock(),
        )

        transcriber = Transcriber(model="base", language="ru")
        result = transcriber.transcribe(tmp_path / "test.ogg")

        assert result == "Привет, мир!"
        mock_model_instance.transcribe.assert_called_once()
    finally:
        transcribe.WhisperModel = original_model
