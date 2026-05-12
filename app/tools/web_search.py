"""Tool `web_search` — DuckDuckGo через `ddgs`.

См. `_docs/tools.md` §4.4.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Mapping

from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

logger = logging.getLogger(__name__)

DEFAULT_TOP_K: int = 5


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Веб-поиск через DuckDuckGo. Возвращает JSON-массив "
        "[{title, href, snippet}, ...]."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    }

    def __init__(
        self,
        *,
        default_top_k: int = DEFAULT_TOP_K,
        max_output_chars: int = 50000,
    ) -> None:
        self._default_top_k = default_top_k
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        query = str(args["query"]).strip()
        if not query:
            raise ToolError("empty query")
        top_k = int(args.get("top_k") or self._default_top_k)
        if top_k <= 0:
            top_k = self._default_top_k

        # Читаем поисковик из настроек пользователя
        search_engine = ctx.user_settings.get_search_engine(ctx.user_id)

        started = time.monotonic()
        logger.info(
            "external.call service=web_search engine=%s top_k=%d",
            search_engine, top_k,
            extra={"service": "web_search", "engine": search_engine,
                   "top_k": top_k},
        )
        try:
            raw = await asyncio.to_thread(
                self._search_sync, query, top_k, search_engine
            )
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            dur_ms = int((time.monotonic() - started) * 1000)
            logger.error(
                "external.fail service=web_search engine=%s dur_ms=%d error=%s",
                search_engine, dur_ms, exc,
                extra={"service": "web_search", "engine": search_engine,
                       "duration_ms": dur_ms, "status": "fail",
                       "error": str(exc)},
            )
            raise ToolError(f"search unavailable: {exc}") from exc

        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "external.ok service=web_search engine=%s dur_ms=%d n_results=%d",
            search_engine, dur_ms, len(raw),
            extra={"service": "web_search", "engine": search_engine,
                   "duration_ms": dur_ms, "status": "ok",
                   "n_results": len(raw)},
        )

        items = [
            {
                "title": r.get("title", ""),
                "href": r.get("href") or r.get("url", ""),
                "snippet": r.get("body") or r.get("snippet", ""),
            }
            for r in raw
        ]
        return truncate_output(json.dumps(items, ensure_ascii=False), self._max_output_chars)

    @staticmethod
    def _search_sync(
        query: str, top_k: int, search_engine: str
    ) -> list[dict[str, Any]]:
        """Выполнить поиск через указанный поисковик.

        Сейчас поддерживается только duckduckgo через ddgs.
        В будущем можно добавить поддержку других поисковиков.
        """
        from ddgs import DDGS  # импорт здесь — упрощает мок в тестах

        # Fallback: если поисковик не duckduckgo, всё равно используем ddgs
        # (в будущем здесь будет логика для разных поисковиков)
        if search_engine != "duckduckgo":
            # Пока только duckduckgo реализован, другие возвращают пустой результат
            # В задаче 3.1 требуется только инфраструктура для выбора
            # Реализация других поисковиков — будущая задача
            return []

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=top_k))
