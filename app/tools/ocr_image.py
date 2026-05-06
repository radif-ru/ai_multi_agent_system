"""Tool `ocr_image` — распознавание текста с одиночных изображений.

См. задачу 2.1 спринта 05.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping

from app.services.ocr import extract_text
from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

logger = logging.getLogger(__name__)


class OcrImageTool(Tool):
    name = "ocr_image"
    description = (
        "Распознать текст с изображения через OCR. "
        "Используйте для точной транскрипции текста (сканы документов, чеки, таблицы). "
        "Для описания сцен или объектов без текста используйте describe_image."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "image_path": {"type": "string"},
            "lang": {"type": "string"},
        },
        "required": ["image_path"],
    }

    def __init__(self, tmp_dir: Path, max_output_chars: int = 8000) -> None:
        self._tmp_dir = tmp_dir.resolve()
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        raw_path = str(args["image_path"])
        lang = args.get("lang")
        return await asyncio.to_thread(self._run_sync, raw_path, lang)

    def _run_sync(self, raw_path: str, lang: str | None) -> str:
        candidate = Path(raw_path)

        # Запрещаем явные `..`-обходы
        if ".." in candidate.parts:
            raise ToolError("путь вне разрешённой директории")

        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise ToolError(f"ошибка разрешения пути: {exc}") from exc

        # Проверяем существование файла
        if not resolved.exists():
            raise ToolError("файл не найден")
        if not resolved.is_file():
            raise ToolError("не является обычным файлом")

        # Проверяем, что путь внутри tmp_dir
        try:
            resolved.relative_to(self._tmp_dir)
        except ValueError:
            raise ToolError("путь вне разрешённой директории")

        # Проверяем расширение
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        if resolved.suffix.lower() not in allowed_extensions:
            raise ToolError(f"неподдерживаемое расширение: {resolved.suffix}")

        # Выполняем OCR через сервис с кешем
        cache_path = resolved.with_suffix(".ocr.txt")
        text = extract_text(image_paths=[resolved], lang=lang, cache_path=cache_path)

        if not text:
            return "OCR не нашёл текста на изображении"

        # Обрезаем до лимита
        return truncate_output(text, self._max_output_chars)
