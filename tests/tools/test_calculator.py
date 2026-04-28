"""Тесты `app.tools.calculator.CalculatorTool`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.calculator import CalculatorTool
from app.tools.errors import ToolError


@pytest.fixture
def ctx() -> SimpleNamespace:
    return SimpleNamespace()


async def test_basic_arithmetic(ctx):
    tool = CalculatorTool()
    assert await tool.run({"expression": "(123 + 456) * 2"}, ctx) == "1158"


async def test_float_result(ctx):
    tool = CalculatorTool()
    out = await tool.run({"expression": "1/4"}, ctx)
    assert out == "0.25"


async def test_division_by_zero_raises(ctx):
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        await tool.run({"expression": "1/0"}, ctx)


async def test_unsupported_expression_raises(ctx):
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        await tool.run({"expression": "__import__('os')"}, ctx)


async def test_syntax_error_raises(ctx):
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        await tool.run({"expression": "2 +"}, ctx)


async def test_attribute_access_blocked(ctx):
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        await tool.run({"expression": "(1).bit_length()"}, ctx)
