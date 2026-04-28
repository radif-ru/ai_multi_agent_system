"""Tool `http_request` — простой GET-запрос.

См. `_docs/tools.md` §4.3.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from app.tools.base import MAX_TOOL_OUTPUT_CHARS, Tool, ToolContext, truncate_output
from app.tools.errors import ToolError

DEFAULT_TIMEOUT: float = 30.0


class HttpRequestTool(Tool):
    name = "http_request"
    description = (
        "Выполнить HTTP GET-запрос по URL и вернуть статус и тело "
        "(усечённое до лимита). Только http/https."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_chars: int = MAX_TOOL_OUTPUT_CHARS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_output_chars = max_output_chars
        self._client = client  # для тестов; иначе создаём per-call

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        url = str(args["url"])
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ToolError("only http/https URLs are allowed")
        if not parsed.netloc:
            raise ToolError("invalid URL")

        try:
            if self._client is not None:
                resp = await self._client.get(url)
            else:
                async with httpx.AsyncClient(
                    timeout=self._timeout, follow_redirects=True, max_redirects=3
                ) as client:
                    resp = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ToolError(f"request timeout: {exc}") from exc
        except httpx.RequestError as exc:
            raise ToolError(f"request failed: {exc}") from exc

        body = resp.text or ""
        out = f"HTTP {resp.status_code}\n{body}"
        return truncate_output(out, self._max_output_chars)
