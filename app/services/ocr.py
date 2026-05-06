"""Сервис OCR для распознавания текста с изображений.

См. задачу 1.1 спринта 05.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# Кеш для доступных языков tesseract
_cached_langs: list[str] | None = None


def get_default_lang() -> str:
    """Получить язык OCR по умолчанию с кешированием."""
    global _cached_langs

    try:
        import pytesseract  # noqa: F401
    except ImportError:
        logger.warning("pytesseract не установлен")
        return "eng"

    if _cached_langs is not None:
        # Используем кешированные языки
        if "rus" in _cached_langs:
            return "rus+eng"
        return "eng"

    try:
        available_langs = pytesseract.get_languages(config='')
        _cached_langs = available_langs
        logger.info("Доступные языки tesseract: %s", available_langs)
        if "rus" in available_langs:
            return "rus+eng"
        return "eng"
    except Exception as exc:
        logger.warning("Ошибка получения языков tesseract, используем eng: %s", exc)
        return "eng"


def extract_text(
    image_paths: Sequence[Path],
    lang: str | None = None,
    cache_path: Path | None = None,
) -> str:
    """Извлечь текст с изображений через OCR.

    Args:
        image_paths: Пути к изображениям.
        lang: Язык OCR (None → автоопределение через get_default_lang).
        cache_path: Путь к файлу кеша (если указан, читает/пишет кеш).

    Returns:
        Склеенный текст со всех изображений.
    """
    if not image_paths:
        return ""

    # Проверяем наличие зависимостей
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        logger.warning("pytesseract не установлен")
        return ""

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        logger.warning("PIL не установлен")
        return ""

    # Если указан путь кеша, проверяем его
    if cache_path is not None and cache_path.exists():
        logger.info("OCR кеш найден: %s", cache_path)
        cached_text = cache_path.read_text(encoding="utf-8")
        if cached_text.strip():
            return cached_text
        logger.info("Кеш пуст, выполняем OCR")

    # Определяем язык
    if lang is None:
        lang = get_default_lang()

    logger.info("OCR для %d изображений, язык=%s", len(image_paths), lang)

    ocr_text_parts = []
    for img_path in image_paths:
        try:
            img = Image.open(img_path)
            ocr_text = pytesseract.image_to_string(img, lang=lang)
            if ocr_text.strip():
                ocr_text_parts.append(ocr_text.strip())
                logger.info("OCR извлёк текст из %s: %d символов", img_path, len(ocr_text))
        except Exception as exc:
            logger.warning("Ошибка OCR для %s: %s", img_path, exc)

    if not ocr_text_parts:
        logger.info("OCR не извлёк текста ни с одного изображения")
        return ""

    result = "\n\n".join(ocr_text_parts)
    logger.info("OCR добавил %d символов текста", len(result))

    # Сохраняем в кеш
    if cache_path is not None:
        try:
            cache_path.write_text(result, encoding="utf-8")
            logger.info("OCR текст сохранён в кеш: %s", cache_path)
        except Exception as exc:
            logger.warning("Не удалось сохранить OCR кеш: %s", exc)

    return result
