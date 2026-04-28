"""Tool `calculator` — безопасное вычисление арифметического выражения.

См. `_docs/tools.md` §4.1.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

from app.tools.base import Tool, ToolContext
from app.tools.errors import ToolError

_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ToolError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        try:
            return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
        except ZeroDivisionError as exc:
            raise ToolError("division by zero") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ToolError(f"Unsupported expression: {ast.dump(node)!r}")


class CalculatorTool(Tool):
    name = "calculator"
    description = (
        "Безопасное вычисление арифметического выражения (без eval/exec). "
        "Поддерживаются + - * / // ** %, унарные +/-."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        expression = str(args["expression"])
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ToolError(f"Syntax error: {exc.msg}") from exc
        result = _safe_eval(tree)
        if isinstance(result, float) and result.is_integer():
            return str(int(result))
        return str(result)
