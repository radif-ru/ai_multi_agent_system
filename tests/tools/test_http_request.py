"""Тесты `app.tools.http_request.HttpRequestTool`."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.tools.errors import ToolError
from app.tools.http_request import HttpRequestTool


@pytest.fixture
def ctx() -> SimpleNamespace:
    return SimpleNamespace()


def _client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, follow_redirects=True)


async def test_success_returns_status_and_body(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, text="ok body")

    tool = HttpRequestTool(client=_client(handler))
    out = await tool.run({"url": "https://example.com/x"}, ctx)
    assert out.startswith("HTTP 200\n")
    assert "ok body" in out


async def test_404_returned_as_string_not_error(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    tool = HttpRequestTool(client=_client(handler))
    out = await tool.run({"url": "https://example.com/missing"}, ctx)
    assert out.startswith("HTTP 404\n")
    assert "missing" in out


async def test_timeout_maps_to_tool_error(ctx):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    tool = HttpRequestTool(client=_client(handler))
    with pytest.raises(ToolError):
        await tool.run({"url": "https://example.com/x"}, ctx)


async def test_non_http_scheme_rejected(ctx):
    tool = HttpRequestTool()
    with pytest.raises(ToolError):
        await tool.run({"url": "file:///etc/passwd"}, ctx)


async def test_invalid_url_rejected(ctx):
    tool = HttpRequestTool()
    with pytest.raises(ToolError):
        await tool.run({"url": "not a url"}, ctx)


async def test_truncation(ctx):
    body = "x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    tool = HttpRequestTool(client=_client(handler), max_output_chars=200)
    out = await tool.run({"url": "https://example.com"}, ctx)
    assert len(out) == 200
    assert out.endswith("[truncated]")
