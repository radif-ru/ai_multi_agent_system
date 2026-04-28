"""Тесты `app.tools.web_search.WebSearchTool`."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.tools.errors import ToolError
from app.tools.web_search import WebSearchTool


@pytest.fixture
def ctx() -> SimpleNamespace:
    return SimpleNamespace()


async def test_success_returns_json(mocker, ctx):
    fake = [
        {"title": "T1", "href": "https://a", "body": "B1"},
        {"title": "T2", "href": "https://b", "body": "B2"},
    ]
    mocker.patch(
        "app.tools.web_search.WebSearchTool._search_sync",
        return_value=fake,
    )
    tool = WebSearchTool()
    out = await tool.run({"query": "hello"}, ctx)
    parsed = json.loads(out)
    assert parsed == [
        {"title": "T1", "href": "https://a", "snippet": "B1"},
        {"title": "T2", "href": "https://b", "snippet": "B2"},
    ]


async def test_empty_result_returns_empty_array(mocker, ctx):
    mocker.patch(
        "app.tools.web_search.WebSearchTool._search_sync",
        return_value=[],
    )
    tool = WebSearchTool()
    assert await tool.run({"query": "nothing"}, ctx) == "[]"


async def test_network_failure_maps_to_tool_error(mocker, ctx):
    mocker.patch(
        "app.tools.web_search.WebSearchTool._search_sync",
        side_effect=RuntimeError("network down"),
    )
    tool = WebSearchTool()
    with pytest.raises(ToolError):
        await tool.run({"query": "x"}, ctx)


async def test_empty_query_rejected(ctx):
    tool = WebSearchTool()
    with pytest.raises(ToolError):
        await tool.run({"query": "  "}, ctx)


async def test_top_k_passed_through(mocker, ctx):
    spy = mocker.patch(
        "app.tools.web_search.WebSearchTool._search_sync",
        return_value=[],
    )
    tool = WebSearchTool()
    await tool.run({"query": "x", "top_k": 3}, ctx)
    spy.assert_called_once_with("x", 3)
