"""Очистка временных файлов (изображений) при архивировании сессии.

См. `_docs/architecture.md` §6.4 (cleanup старых изображений).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.events import ConversationArchived

logger = logging.getLogger(__name__)


def _cleanup_tmp_images(tmp_dir: Path) -> int:
    """Удалить изображения старше 1 часа из временной директории.

    Args:
        tmp_dir: Директория с временными файлами (Settings.tmp_base_dir).

    Returns:
        Количество удалённых файлов.
    """
    if not tmp_dir.exists():
        return 0

    import time

    now = time.time()
    one_hour = 3600
    deleted = 0

    for root, dirs, files in os.walk(tmp_dir):
        for file in files:
            file_path = Path(root) / file
            # Проверяем, что это изображение (по расширению)
            if file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                try:
                    file_mtime = file_path.stat().st_mtime
                    if now - file_mtime > one_hour:
                        file_path.unlink()
                        deleted += 1
                        logger.debug("удалён старый tmp-файл: %s", file_path)
                except OSError:
                    logger.warning("не удалось удалить tmp-файл: %s", file_path)

    if deleted > 0:
        logger.info("cleanup tmp-images: удалено %d файлов из %s", deleted, tmp_dir)

    return deleted


async def on_conversation_archived_cleanup(
    event: "ConversationArchived",
    *,
    tmp_dir: Path,
) -> None:
    """Подписчик на событие ConversationArchived для очистки временных изображений.

    При успешном архивировании сессии удаляет изображения старше 1 часа
    из временной директории.

    Args:
        event: Событие завершения архивирования.
        tmp_dir: Директория с временными файлами.
    """
    try:
        deleted = _cleanup_tmp_images(tmp_dir)
        if deleted > 0:
            logger.info(
                "on_conversation_archived_cleanup: user_id=%s conversation_id=%s удалено %d tmp-файлов",
                event.user.id,
                event.conversation_id,
                deleted,
            )
    except Exception:
        logger.warning(
            "on_conversation_archived_cleanup не удалась: user_id=%s conversation_id=%s",
            event.user.id,
            event.conversation_id,
            exc_info=True,
        )
