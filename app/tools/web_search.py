"""Tool `web_search` — DuckDuckGo через `ddgs`.

См. `_docs/tools.md` §4.4.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

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

        try:
            raw = await asyncio.to_thread(
                self._search_sync, query, top_k, search_engine
            )
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"search unavailable: {exc}") from exc

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
