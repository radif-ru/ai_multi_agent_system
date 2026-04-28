"""Тесты `app.tools.memory_search.MemorySearchTool`."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.llm import LLMUnavailable
from app.services.memory import MemoryUnavailable
from app.tools.errors import ToolError
from app.tools.memory_search import MemorySearchTool


def _ctx(mocker, *, search_return=None, search_exc=None, embed_exc=None):
    llm = SimpleNamespace(embed=mocker.AsyncMock(return_value=[0.1, 0.2, 0.3]))
    if embed_exc is not None:
        llm.embed = mocker.AsyncMock(side_effect=embed_exc)
    if search_exc is not None:
        sm = SimpleNamespace(search=mocker.AsyncMock(side_effect=search_exc))
    else:
        sm = SimpleNamespace(search=mocker.AsyncMock(return_value=search_return or []))
    settings = SimpleNamespace(memory_search_top_k=5, embedding_model="nomic-embed-text")
    return SimpleNamespace(
        user_id=42, chat_id=42, conversation_id="c",
        settings=settings, llm=llm, semantic_memory=sm, skills=None,
    )


async def test_success_formats_results(mocker):
    rows = [
        {"text": "fact1", "conversation_id": "c1", "created_at": "2026-04-28", "distance": 0.1},
        {"text": "fact2", "conversation_id": "c2", "created_at": "2026-04-29", "distance": 0.2},
    ]
    ctx = _ctx(mocker, search_return=rows)
    tool = MemorySearchTool()
    out = await tool.run({"query": "what?"}, ctx)
    parsed = json.loads(out)
    assert parsed == rows
    ctx.llm.embed.assert_awaited_once_with("what?", model="nomic-embed-text")
    ctx.semantic_memory.search.assert_awaited_once_with(
        [0.1, 0.2, 0.3], top_k=5, scope_user_id=42
    )


async def test_empty_query_rejected(mocker):
    ctx = _ctx(mocker)
    tool = MemorySearchTool()
    with pytest.raises(ToolError):
        await tool.run({"query": ""}, ctx)


async def test_memory_unavailable_maps_to_tool_error(mocker):
    ctx = _ctx(mocker, search_exc=MemoryUnavailable("no ext"))
    tool = MemorySearchTool()
    with pytest.raises(ToolError, match="long-term memory unavailable"):
        await tool.run({"query": "hi"}, ctx)


async def test_embedding_failure_maps_to_tool_error(mocker):
    ctx = _ctx(mocker, embed_exc=LLMUnavailable("ollama down"))
    tool = MemorySearchTool()
    with pytest.raises(ToolError):
        await tool.run({"query": "hi"}, ctx)


async def test_top_k_argument_overrides_default(mocker):
    ctx = _ctx(mocker, search_return=[])
    tool = MemorySearchTool()
    await tool.run({"query": "hi", "top_k": 2}, ctx)
    ctx.semantic_memory.search.assert_awaited_once_with(
        [0.1, 0.2, 0.3], top_k=2, scope_user_id=42
    )
