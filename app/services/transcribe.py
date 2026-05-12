"""Сервис транскрипции речи через faster-whisper.

См. задачу 3.4 спринта 02.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore

logger = logging.getLogger(__name__)


class TranscriberUnavailableError(Exception):
    """faster-whisper не установлен."""

    pass


class Transcriber:
    """Обёртка над faster-whisper для транскрипции аудио."""

    def __init__(self, model: str = "base", language: str = "ru") -> None:
        """Инициализировать транскрибер.

        Args:
            model: Название модели Whisper (base, small, medium, large).
            language: Язык для распознавания (ru, en, etc.).

        Raises:
            TranscriberUnavailableError: Если faster-whisper не установлен.
        """
        if WhisperModel is None:
            raise TranscriberUnavailableError("faster-whisper not installed")
        self._model = model
        self._language = language
        self._whisper_model = WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: Path) -> str:
        """Транскрибировать аудиофайл.

        Args:
            audio_path: Путь к аудиофайлу (.ogg, .opus, .wav, etc.).

        Returns:
            Распознанный текст.

        Raises:
            Exception: При ошибке транскрипции.
        """
        started = time.monotonic()
        logger.info(
            "external.call service=transcribe model=%s language=%s",
            self._model,
            self._language,
            extra={
                "service": "transcribe",
                "model": self._model,
                "language": self._language,
            },
        )

        try:
            segments, info = self._whisper_model.transcribe(
                audio_path, language=self._language
            )
            text = "".join(s.text for s in segments).strip()
        except Exception as exc:
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.error(
                "external.fail service=transcribe model=%s dur_ms=%d error=%s",
                self._model,
                dur_ms,
                exc,
                extra={
                    "service": "transcribe",
                    "model": self._model,
                    "duration_ms": dur_ms,
                    "status": "fail",
                    "error": str(exc),
                },
            )
            raise

        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "external.ok service=transcribe model=%s dur_ms=%d len_out=%d",
            self._model,
            dur_ms,
            len(text),
            extra={
                "service": "transcribe",
                "model": self._model,
                "duration_ms": dur_ms,
                "status": "ok",
                "len_out": len(text),
            },
        )
        return text


def is_transcriber_available() -> bool:
    """Проверить, доступен ли faster-whisper."""
    return WhisperModel is not None
