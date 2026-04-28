"""Тесты `app.tools.registry.ToolRegistry`.

Покрытие — по `_docs/testing.md` §3.5.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from app.tools.base import MAX_TOOL_OUTPUT_CHARS, Tool
from app.tools.errors import ArgsValidationError, ToolError, ToolNotFound
from app.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echo back the text."
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["text"],
    }

    def __init__(self, output: str = "") -> None:
        self._output = output

    async def run(self, args: Mapping[str, Any], ctx) -> str:
        return self._output or str(args["text"])


class _BoomTool(Tool):
    name = "boom"
    description = "Always fails."
    args_schema: Mapping[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def run(self, args: Mapping[str, Any], ctx) -> str:
        raise ToolError("kaboom")


@pytest.fixture
def ctx() -> SimpleNamespace:
    return SimpleNamespace(
        user_id=1, chat_id=1, conversation_id="c", settings=None,
        llm=None, semantic_memory=None, skills=None,
    )


async def test_get_unknown_raises_not_found(ctx):
    reg = ToolRegistry([_EchoTool()])
    with pytest.raises(ToolNotFound):
        reg.get("missing")
    with pytest.raises(ToolNotFound):
        await reg.execute("missing", {}, ctx)


async def test_args_validation_missing_required(ctx):
    reg = ToolRegistry([_EchoTool()])
    with pytest.raises(ArgsValidationError):
        await reg.execute("echo", {}, ctx)


async def test_args_validation_wrong_type(ctx):
    reg = ToolRegistry([_EchoTool()])
    with pytest.raises(ArgsValidationError):
        await reg.execute("echo", {"text": 42}, ctx)


async def test_args_validation_integer_rejects_bool(ctx):
    reg = ToolRegistry([_EchoTool()])
    with pytest.raises(ArgsValidationError):
        await reg.execute("echo", {"text": "x", "n": True}, ctx)


async def test_execute_success_logs_status_ok(ctx, caplog):
    reg = ToolRegistry([_EchoTool()])
    with caplog.at_level("INFO", logger="app.tools.registry"):
        out = await reg.execute("echo", {"text": "hi"}, ctx)
    assert out == "hi"
    assert any(
        "tool=echo" in r.message and "status=ok" in r.message
        for r in caplog.records
    )


async def test_execute_tool_error_propagates_and_logs_error(ctx, caplog):
    reg = ToolRegistry([_BoomTool()])
    with caplog.at_level("INFO", logger="app.tools.registry"):
        with pytest.raises(ToolError):
            await reg.execute("boom", {}, ctx)
    assert any(
        "tool=boom" in r.message and "status=error" in r.message
        for r in caplog.records
    )


async def test_execute_truncates_output(ctx):
    long = "x" * (MAX_TOOL_OUTPUT_CHARS + 100)
    reg = ToolRegistry([_EchoTool(output=long)])
    out = await reg.execute("echo", {"text": "ignored"}, ctx)
    assert len(out) == MAX_TOOL_OUTPUT_CHARS
    assert out.endswith("[truncated]")


def test_list_descriptions_sorted_and_complete():
    reg = ToolRegistry([_BoomTool(), _EchoTool()])
    descs = reg.list_descriptions()
    assert [d["name"] for d in descs] == ["boom", "echo"]
    assert {"name", "description", "args_schema"} <= set(descs[0])


def test_duplicate_name_rejected():
    with pytest.raises(ValueError):
        ToolRegistry([_EchoTool(), _EchoTool()])
