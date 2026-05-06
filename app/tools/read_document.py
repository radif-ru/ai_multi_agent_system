"""Tool `read_document` — чтение документов (PDF/TXT/MD) из временной директории.

См. задачу 3.2 спринта 02.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

from app.services.ocr import extract_text, get_default_lang
from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

logger = logging.getLogger(__name__)


class ReadDocumentTool(Tool):
    name = "read_document"
    description = (
        "Прочитать содержимое документа (PDF, TXT, MD, JPG, PNG) из временной директории. "
        "Для PDF используется текстовое извлечение, для TXT/MD — прямое чтение. "
        "Для изображений (JPG, PNG) используется OCR через tesseract (если включён). "
        "Возврат — текст, усечённый до лимита."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 50000},
        },
        "required": ["path"],
    }

    def __init__(
        self,
        tmp_files_dir: Path,
        max_file_size_mb: int = 20,
        max_document_chars: int = 50000,
        max_images: int = 20,
        ocr_enabled: bool = False,
        ocr_min_text_threshold: int = 100,
    ) -> None:
        self._tmp_dir = tmp_files_dir.resolve()
        self._max_file_size = max_file_size_mb * 1024 * 1024
        self._max_document_chars = max_document_chars
        self._max_images = max_images
        self._ocr_enabled = ocr_enabled
        self._ocr_min_text_threshold = ocr_min_text_threshold

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        raw_path = str(args["path"])
        max_chars = int(args.get("max_chars", 50000))
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

        # Проверяем размер файла
        file_size = resolved.stat().st_size
        if file_size > self._max_file_size:
            raise ToolError(f"файл слишком большой ({file_size / 1024 / 1024:.1f}MB), максимальный размер {self._max_file_size / 1024 / 1024:.0f}MB")

        # Определяем тип по расширению
        suffix = resolved.suffix.lower()

        if suffix == ".pdf":
            if PdfReader is None:
                raise ToolError("pypdf не установлен")
            return self._read_pdf(resolved, max_chars)
        elif suffix in (".txt", ".md"):
            return self._read_text(resolved, max_chars)
        elif suffix in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
            return self._read_image(resolved, max_chars)
        else:
            raise ToolError(f"неподдерживаемый тип файла: {suffix}")

    def _read_pdf(self, path: Path, max_chars: int) -> str:
        """Извлечь текст и картинки из PDF через pypdf."""
        try:
            reader = PdfReader(path)
            max_images = self._max_images
            logger.info("Чтение PDF: %s, страниц=%d, max_chars=%d, max_images=%d, ocr=%s",
                       path, len(reader.pages), max_chars, max_images, self._ocr_enabled)
            text_parts = []
            total_chars = 0
            image_paths = []

            for page_num, page in enumerate(reader.pages):
                # Извлекаем текст
                page_text = page.extract_text() or ""
                if total_chars + len(page_text) > max_chars:
                    remaining = max_chars - total_chars
                    text_parts.append(page_text[:remaining])
                    break
                text_parts.append(page_text)
                total_chars += len(page_text)

                # Извлекаем картинки
                if "/Resources" in page:
                    resources = page["/Resources"]
                    if "/XObject" in resources:
                        xobject = resources["/XObject"].get_object()
                        for obj_name in xobject:
                            # Ограничиваем количество извлекаемых картинок для всего документа
                            if len(image_paths) >= max_images:
                                break
                            obj = xobject[obj_name]
                            if "/Subtype" in obj and obj["/Subtype"] == "/Image":
                                try:
                                    # Сохраняем картинку
                                    image_data = obj.get_data()
                                    image_ext = self._get_image_extension(obj)
                                    # Очищаем obj_name от недопустимых символов для файловой системы
                                    clean_obj_name = str(obj_name).replace("/", "_").replace("\\", "_")
                                    image_filename = f"{path.stem}_page{page_num}_{clean_obj_name}{image_ext}"
                                    image_path = path.parent / image_filename
                                    
                                    # Проверяем существует ли картинка уже
                                    if image_path.exists():
                                        logger.info("Картинка уже существует: %s", image_path)
                                        image_paths.append(str(image_path))
                                    else:
                                        with open(image_path, "wb") as f:
                                            f.write(image_data)
                                        image_paths.append(str(image_path))
                                        logger.info("Извлечена картинка из PDF: %s", image_path)
                                except Exception as exc:
                                    logger.warning("Ошибка извлечения картинки: %s", exc)
                
                # Если достигнут лимит картинок, прерываем обработку страниц
                if len(image_paths) >= max_images:
                    logger.info("Достигнут лимит извлечения картинок (%d)", max_images)
                    break

            text = "\n".join(text_parts)

            # Если OCR включен и текста очень мало, извлекаем текст из картинок через сервис
            ocr_successful = False
            if self._ocr_enabled and len(text) < self._ocr_min_text_threshold and image_paths:
                ocr_cache_path = path.with_suffix(".ocr.txt")
                ocr_text = extract_text(
                    image_paths=[Path(p) for p in image_paths],
                    cache_path=ocr_cache_path,
                )
                if ocr_text:
                    text += f"\n\n[OCR текст из изображений:]\n{ocr_text}"
                    logger.info("OCR добавил %d символов текста", len(ocr_text))
                    ocr_successful = True
            
            result = truncate_output(text, max_chars)
            
            logger.info("PDF прочитан: текст=%d символов, картинок=%d", len(text), len(image_paths))
            
            # Возвращаем информацию о картинках только если OCR не сработал или текста мало
            if image_paths and not ocr_successful:
                # Если текста очень мало (< 100 символов), это скан - возвращаем только первую картинку
                if len(text) < 100:
                    logger.warning("PDF похоже на скан (текст=%d символов), возвращаем только первую картинку", len(text))
                    result += f"\n\n[PDF содержит {len(image_paths)} изображений. Текст не извлечён. Первая картинка: {image_paths[0]}]"
                else:
                    result += f"\n\n[PDF содержит {len(image_paths)} изображений: {', '.join(image_paths)}]"
            
            return result
        except Exception as exc:
            logger.error("Ошибка чтения PDF: %s", exc)
            raise ToolError(f"ошибка чтения PDF: {exc}") from exc

    def _get_image_extension(self, image_obj: Any) -> str:
        """Определить расширение изображения по его типу."""
        if "/Filter" in image_obj:
            filter_type = image_obj["/Filter"]
            if isinstance(filter_type, str):
                if filter_type == "/DCTDecode":
                    return ".jpg"
                elif filter_type == "/FlateDecode":
                    return ".png"
            elif isinstance(filter_type, list):
                if "/DCTDecode" in filter_type:
                    return ".jpg"
        return ".png"

    def _read_text(self, path: Path, max_chars: int) -> str:
        """Прочитать текстовый файл."""
        try:
            text = path.read_text(encoding="utf-8")
            return truncate_output(text, max_chars)
        except UnicodeDecodeError:
            raise ToolError("файл не является валидным UTF-8 текстом")
        except OSError as exc:
            raise ToolError(f"ошибка чтения файла: {exc}") from exc

    def _read_image(self, path: Path, max_chars: int) -> str:
        """Распознать текст с изображения через tesseract."""
        if not self._ocr_enabled:
            raise ToolError("OCR отключён. Включите DOCUMENT_OCR_ENABLED в настройках.")

        # Проверяем кеш OCR
        ocr_cache_path = path.with_suffix(".ocr.txt")
        text = extract_text(image_paths=[path], cache_path=ocr_cache_path)

        if not text:
            raise ToolError("OCR не смог извлечь текст с изображения")

        # Проверяем, что это не просто изображение без текста
        if len(text.strip()) < 50:
            logger.warning("OCR извлёк очень мало текста (%d символов), похоже на обычное изображение", len(text))
            text = f"[OCR извлёк очень мало текста ({len(text)} символов). Если это обычное изображение без текста, загрузите его как изображение в Telegram, а не как файл.]\n\n{text}"

        return truncate_output(text, max_chars)
