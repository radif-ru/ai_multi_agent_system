"""Tool `ocr_image` — распознавание текста с одиночных изображений.

См. задачу 2.1 спринта 05.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping

from app.security import file_id_not_found_message, get_global_mapper
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
            "file_id": {"type": "string"},
            "lang": {"type": "string"},
        },
        "required": [],
    }

    def __init__(self, tmp_dir: Path, max_output_chars: int = 8000) -> None:
        self._tmp_dir = tmp_dir.resolve()
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        # Если передан file_id, восстанавливаем путь через FileIdMapper
        if "file_id" in args and args["file_id"]:
            mapper = get_global_mapper()
            path = mapper.get_path(str(args["file_id"]))
            if path is None:
                raise ToolError(file_id_not_found_message(str(args['file_id'])))
            raw_path = str(path)
        elif "image_path" in args and args["image_path"]:
            raw_path = str(args["image_path"])
        else:
            raise ToolError("требуется image_path или file_id")

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

        # Дисковый кеш `.ocr.txt` убран (задача 06.3-bis.4):
        # результат OCR попадает в `dialog_journal.content` через goal.
        text = extract_text(image_paths=[resolved], lang=lang)

        if not text:
            return "OCR не нашёл текста на изображении"

        # Обрезаем до лимита
        return truncate_output(text, self._max_output_chars)
