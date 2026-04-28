"""LLM-клиент над Ollama.

См. `_docs/architecture.md` §3.4 и `_docs/testing.md` §3.2.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Sequence

import httpx
from ollama import AsyncClient, ResponseError

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Базовое исключение LLM-слоя."""


class LLMTimeout(LLMError):
    """Таймаут при обращении к LLM."""


class LLMUnavailable(LLMError):
    """LLM недоступна (connection refused и т.п.)."""


class LLMBadResponse(LLMError):
    """LLM вернула некорректный ответ (битый JSON, 4xx/5xx, пустой ответ)."""


class OllamaClient:
    """Async-клиент над `ollama.AsyncClient` с явной обработкой ошибок."""

    def __init__(self, *, base_url: str, timeout: float) -> None:
        self._client = AsyncClient(host=base_url, timeout=timeout)

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.0,
    ) -> str:
        len_in = sum(len(m.get("content", "")) for m in messages)
        started = time.monotonic()
        try:
            resp = await self._client.chat(
                model=model,
                messages=list(messages),
                options={"temperature": temperature},
            )
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            self._log_call("chat", model, len_in, 0, started, "timeout")
            raise LLMTimeout(f"chat timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            self._log_call("chat", model, len_in, 0, started, "unavailable")
            raise LLMUnavailable(f"chat connection error: {exc}") from exc
        except ResponseError as exc:
            self._log_call("chat", model, len_in, 0, started, f"http {exc.status_code}")
            if exc.status_code == 404:
                raise LLMBadResponse(f"model not found: {exc.error}") from exc
            raise LLMBadResponse(f"chat http error {exc.status_code}: {exc.error}") from exc

        content = (resp.message.content or "") if resp.message else ""
        if not content:
            self._log_call("chat", model, len_in, 0, started, "empty")
            raise LLMBadResponse("chat empty response")
        self._log_call("chat", model, len_in, len(content), started, "ok")
        return content

    async def embed(self, text: str, *, model: str) -> list[float]:
        len_in = len(text)
        started = time.monotonic()
        try:
            resp = await self._client.embeddings(model=model, prompt=text)
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            self._log_call("embed", model, len_in, 0, started, "timeout")
            raise LLMTimeout(f"embed timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            self._log_call("embed", model, len_in, 0, started, "unavailable")
            raise LLMUnavailable(f"embed connection error: {exc}") from exc
        except ResponseError as exc:
            self._log_call("embed", model, len_in, 0, started, f"http {exc.status_code}")
            if exc.status_code == 404:
                raise LLMBadResponse(f"embedding model not found: {exc.error}") from exc
            raise LLMBadResponse(f"embed http error {exc.status_code}: {exc.error}") from exc

        embedding = list(resp.embedding or [])
        if not embedding:
            self._log_call("embed", model, len_in, 0, started, "empty")
            raise LLMBadResponse("embed empty response")
        self._log_call("embed", model, len_in, len(embedding), started, "ok")
        return embedding

    async def close(self) -> None:
        # ollama.AsyncClient наследует httpx.AsyncClient; aclose закрывает соединения.
        aclose = getattr(self._client, "aclose", None)
        if aclose is not None:
            await aclose()

    @staticmethod
    def estimate_tokens(value: str | Sequence[dict[str, Any]]) -> int:
        if isinstance(value, str):
            return max(1, len(value) // 4)
        total = sum(len(m.get("content", "")) for m in value)
        return max(1, total // 4)

    @staticmethod
    def _log_call(
        kind: str,
        model: str,
        len_in: int,
        len_out: int,
        started: float,
        status: str,
    ) -> None:
        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "llm kind=%s model=%s len_in=%d len_out=%d dur_ms=%d status=%s",
            kind,
            model,
            len_in,
            len_out,
            dur_ms,
            status,
        )
