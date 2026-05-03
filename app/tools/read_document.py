"""Tool `read_document` — чтение документов (PDF/TXT/MD) из временной директории.

См. задачу 3.2 спринта 02.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError


class ReadDocumentTool(Tool):
    name = "read_document"
    description = (
        "Прочитать содержимое документа (PDF, TXT, MD) из временной директории. "
        "Для PDF используется текстовое извлечение, для TXT/MD — прямое чтение. "
        "Возврат — текст, усечённый до лимита."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000},
        },
        "required": ["path"],
    }

    def __init__(self, tmp_files_dir: Path) -> None:
        self._tmp_dir = tmp_files_dir.resolve()

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        raw_path = str(args["path"])
        max_chars = int(args.get("max_chars", 8000))
        return await asyncio.to_thread(self._read_sync, raw_path, max_chars)

    def _read_sync(self, raw_path: str, max_chars: int) -> str:
        candidate = Path(raw_path)

        # Запрещаем явные `..`-обходы
        if ".." in candidate.parts:
            raise ToolError("путь вне разрешённой директории")

        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise ToolError(f"ошибка разрешения пути: {exc}") from exc

        # Сначала проверяем существование файла
        if not resolved.exists():
            raise ToolError("файл не найден")
        if not resolved.is_file():
            raise ToolError("не является обычным файлом")

        # Проверяем, что путь внутри tmp_files_dir
        try:
            resolved.relative_to(self._tmp_dir)
        except ValueError:
            raise ToolError("путь вне разрешённой директории")

        # Определяем тип по расширению
        suffix = resolved.suffix.lower()

        if suffix == ".pdf":
            if PdfReader is None:
                raise ToolError("pypdf не установлен")
            return self._read_pdf(resolved, max_chars)
        elif suffix in (".txt", ".md"):
            return self._read_text(resolved, max_chars)
        else:
            raise ToolError(f"неподдерживаемый тип файла: {suffix}")

    def _read_pdf(self, path: Path, max_chars: int) -> str:
        """Извлечь текст из PDF через pypdf."""
        try:
            reader = PdfReader(path)
            text_parts = []
            total_chars = 0

            for page in reader.pages:
                page_text = page.extract_text() or ""
                if total_chars + len(page_text) > max_chars:
                    remaining = max_chars - total_chars
                    text_parts.append(page_text[:remaining])
                    break
                text_parts.append(page_text)
                total_chars += len(page_text)

            text = "\n".join(text_parts)
            return truncate_output(text, max_chars)
        except Exception as exc:
            raise ToolError(f"ошибка чтения PDF: {exc}") from exc

    def _read_text(self, path: Path, max_chars: int) -> str:
        """Прочитать текстовый файл."""
        try:
            text = path.read_text(encoding="utf-8")
            return truncate_output(text, max_chars)
        except UnicodeDecodeError:
            raise ToolError("файл не является валидным UTF-8 текстом")
        except OSError as exc:
            raise ToolError(f"ошибка чтения файла: {exc}") from exc
