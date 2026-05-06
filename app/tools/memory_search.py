"""Tool `memory_search` — поиск в долгосрочной семантической памяти.

См. `_docs/tools.md` §4.5.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.services.llm import LLMError
from app.services.memory import MemoryUnavailable
from app.tools.base import Tool, ToolContext, truncate_output
from app.tools.errors import ToolError


class MemorySearchTool(Tool):
    name = "memory_search"
    description = (
        "Поиск в долгосрочной семантической памяти (саммари прошлых сессий). "
        "Возвращает JSON-массив [{text, conversation_id, created_at, distance}, ...]."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    }

    def __init__(self, *, max_output_chars: int = 50000) -> None:
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        query = str(args["query"]).strip()
        if not query:
            raise ToolError("empty query")
        settings = ctx.settings
        top_k = int(args.get("top_k") or settings.memory_search_top_k)

        try:
            embedding = await ctx.llm.embed(query, model=settings.embedding_model)
        except LLMError as exc:
            raise ToolError(f"embedding failed: {exc}") from exc

        try:
            rows = await ctx.semantic_memory.search(
                embedding, top_k=top_k, scope_user_id=ctx.user_id
            )
        except MemoryUnavailable as exc:
            raise ToolError("long-term memory unavailable") from exc

        items = [
            {
                "text": r["text"],
                "conversation_id": r["conversation_id"],
                "created_at": r["created_at"],
                "distance": r["distance"],
            }
            for r in rows
        ]
        return truncate_output(json.dumps(items, ensure_ascii=False), self._max_output_chars)
