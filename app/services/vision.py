"""Сервис описания изображений через Ollama vision API.

См. задачу 3.5 спринта 02.
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from app.services.llm import OllamaClient

logger = logging.getLogger(__name__)


class VisionUnavailableError(Exception):
    """Vision-модель не настроена."""

    pass


class Vision:
    """Обёртка над OllamaClient для описания изображений."""

    def __init__(self, ollama: OllamaClient, model: str) -> None:
        """Инициализировать vision-сервис.

        Args:
            ollama: Экземпляр OllamaClient.
            model: Название vision-модели (например, llava:7b).
        """
        self._ollama = ollama
        self._model = model

    async def describe(self, image_path: Path, caption: str = "") -> str:
        """Описать изображение.

        Args:
            image_path: Путь к изображению.
            caption: Caption из Telegram (если есть).

        Returns:
            Описание изображения.

        Raises:
            VisionUnavailableError: Если модель не настроена.
            Exception: При ошибке описания.
        """
        started = time.monotonic()
        logger.info(
            "external.call service=vision model=%s",
            self._model,
            extra={"service": "vision", "model": self._model},
        )

        # Читаем изображение и кодируем в base64
        try:
            with image_path.open("rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")
        except OSError as exc:
            logger.error(
                "external.fail service=vision model=%s error=%s",
                self._model, exc,
                extra={"service": "vision", "model": self._model,
                       "status": "fail", "error": str(exc)},
            )
            raise

        # Формируем prompt
        prompt = "Опиши, что изображено на этой картинке."
        if caption:
            prompt += f" Caption: {caption}"

        # Вызываем Ollama API с изображением внутри сообщения
        try:
            # Изображения передаются внутри сообщения, а не как отдельный параметр
            response = await self._ollama.chat(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64]
                }],
            )
            description = response.strip()
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "external.ok service=vision model=%s dur_ms=%d len_out=%d",
                self._model, dur_ms, len(description),
                extra={"service": "vision", "model": self._model,
                       "duration_ms": dur_ms, "status": "ok",
                       "len_out": len(description)},
            )
            return description
        except Exception as exc:
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.error(
                "external.fail service=vision model=%s dur_ms=%d error=%s",
                self._model, dur_ms, exc,
                extra={"service": "vision", "model": self._model,
                       "duration_ms": dur_ms, "status": "fail",
                       "error": str(exc)},
            )
            raise
