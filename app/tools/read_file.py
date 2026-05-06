"""Tool `read_file` — чтение файла из whitelisted-каталогов.

См. `_docs/tools.md` §4.2.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.security import get_global_mapper
from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

DEFAULT_MAX_FILE_BYTES: int = 1024 * 1024  # 1 MiB


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Прочитать содержимое UTF-8 файла из разрешённых каталогов "
        "(по умолчанию `data/`). Возврат — текст, усечённый до лимита."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "file_id": {"type": "string"},
        },
        "required": [],
    }

    def __init__(
        self,
        allowed_dirs: Iterable[str | Path] | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_output_chars: int = 50000,
    ) -> None:
        if allowed_dirs is None:
            allowed_dirs = [Path("data")]
        self._allowed: list[Path] = [Path(p).resolve() for p in allowed_dirs]
        self._max_bytes = max_bytes
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        # Если передан file_id, восстанавливаем путь через FileIdMapper
        if "file_id" in args and args["file_id"]:
            mapper = get_global_mapper()
            path = mapper.get_path(str(args["file_id"]))
            if path is None:
                raise ToolError(f"file_id {args['file_id']} не найден")
            raw = str(path)
        elif "path" in args and args["path"]:
            raw = str(args["path"])
        else:
            raise ToolError("требуется path или file_id")
        return await asyncio.to_thread(self._read_sync, raw)

    def _read_sync(self, raw: str) -> str:
        candidate = Path(raw)
        # Запрещаем явные `..`-обходы.
        if ".." in candidate.parts:
            raise ToolError("path not allowed")
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise ToolError(f"path resolve error: {exc}") from exc

        # Запрещаем системные пути
        system_paths = ["/etc", "/sys", "/proc", "/root/.ssh", "/home/*/.ssh"]
        for sys_path in system_paths:
            if str(resolved).startswith(sys_path):
                raise ToolError("системный путь не разрешён")

        if not any(self._is_within(resolved, root) for root in self._allowed):
            raise ToolError("path not allowed")

        if not resolved.exists():
            raise ToolError("file not found")
        if not resolved.is_file():
            raise ToolError("not a regular file")

        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise ToolError(f"stat error: {exc}") from exc
        if size > self._max_bytes:
            raise ToolError(f"file too large: {size} > {self._max_bytes} bytes")

        try:
            data = resolved.read_bytes()
        except OSError as exc:
            raise ToolError(f"read error: {exc}") from exc
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError("binary file not supported") from exc

        return truncate_output(text, self._max_output_chars)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
