"""Tool `describe_image` — повторное описание изображения по пути.

См. задачу 1.5 спринта 03.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.security import get_global_mapper
from app.services.vision import Vision
from app.tools.base import Tool, ToolContext
from app.tools.errors import ToolError


class DescribeImageTool(Tool):
    name = "describe_image"
    description = (
        "Повторно описать изображение по пути к файлу или file_id. "
        "Используется для уточнения деталей после первичного описания. "
        "Путь должен быть в каталоге tmp/."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "image_path": {"type": "string"},
            "file_id": {"type": "string"},
            "caption": {"type": "string"},
        },
        "required": [],
    }

    def __init__(self, *, tmp_dir: str = "tmp") -> None:
        self._tmp_dir = Path(tmp_dir).resolve()

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        # Если передан file_id, восстанавливаем путь через FileIdMapper
        if "file_id" in args and args["file_id"]:
            mapper = get_global_mapper()
            path = mapper.get_path(str(args["file_id"]))
            if path is None:
                raise ToolError(f"file_id {args['file_id']} не найден")
            raw_path = str(path)
        elif "image_path" in args and args["image_path"]:
            raw_path = str(args["image_path"])
        else:
            raise ToolError("требуется image_path или file_id")
        
        caption = str(args.get("caption", ""))

        # Валидация пути (синхронная)
        candidate = Path(raw_path)

        # Запрещаем явные `..`-обходы.
        if ".." in candidate.parts:
            raise ToolError("path not allowed")

        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise ToolError(f"path resolve error: {exc}") from exc

        # Проверяем, что путь в tmp/
        if not self._is_within(resolved, self._tmp_dir):
            raise ToolError("path not allowed: must be in tmp/")

        if not resolved.exists():
            raise ToolError("file not found")
        if not resolved.is_file():
            raise ToolError("not a regular file")

        # Проверяем, что это изображение (по расширению)
        if resolved.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            raise ToolError("not an image file")

        # Проверяем LLM
        if ctx.llm is None:
            raise ToolError("LLM unavailable for vision")

        # Вызываем Vision
        vision = Vision(ollama=ctx.llm, model=ctx.settings.vision_model or "")
        try:
            description = await vision.describe(resolved, caption=caption)
        except Exception as exc:
            raise ToolError(f"vision description failed: {exc}") from exc

        return description

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
