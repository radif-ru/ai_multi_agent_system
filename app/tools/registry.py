"""Реестр tool'ов и единая точка входа `execute`.

См. `_docs/tools.md` §3 и `_docs/testing.md` §3.5.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Mapping

from app.tools.base import (
    MAX_TOOL_OUTPUT_CHARS,
    Tool,
    ToolContext,
    truncate_output,
)
from app.tools.errors import ArgsValidationError, ToolError, ToolNotFound

logger = logging.getLogger(__name__)


_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list, tuple),
    "null": (type(None),),
}


def _validate_args(schema: Mapping[str, Any], args: Mapping[str, Any]) -> None:
    """Минимальный валидатор: type=object, required, простые типы свойств.

    Достаточно для MVP-набора tools (см. `_docs/tools.md`).
    """

    if schema.get("type") != "object":
        # Контракт: схема — всегда object с properties.
        raise ArgsValidationError("args_schema must be an object schema")
    if not isinstance(args, Mapping):
        raise ArgsValidationError("args must be an object")

    for required in schema.get("required", []) or []:
        if required not in args:
            raise ArgsValidationError(f"missing required arg: '{required}'")

    properties = schema.get("properties", {}) or {}
    for key, value in args.items():
        prop = properties.get(key)
        if not prop:
            continue
        ptype = prop.get("type")
        if ptype is None:
            continue
        types = _PY_TYPES.get(ptype)
        if types is None:
            continue
        # bool is subclass of int — отдельно охраняемся.
        if ptype == "integer" and isinstance(value, bool):
            raise ArgsValidationError(f"arg '{key}' must be integer, got bool")
        if not isinstance(value, types):
            raise ArgsValidationError(
                f"arg '{key}' must be {ptype}, got {type(value).__name__}"
            )


class ToolRegistry:
    """Хранит tool'ы и единственная точка их вызова из `Executor`."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools:
            if t.name in self._tools:
                raise ValueError(f"duplicate tool name: {t.name}")
            self._tools[t.name] = t

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFound(name) from exc

    def list_descriptions(self) -> list[dict[str, Any]]:
        # Стабильный порядок — алфавитный по имени.
        return [
            {
                "name": t.name,
                "description": t.description,
                "args_schema": dict(t.args_schema),
            }
            for t in sorted(self._tools.values(), key=lambda x: x.name)
        ]

    async def execute(
        self,
        name: str,
        args: Mapping[str, Any],
        ctx: ToolContext,
    ) -> str:
        started = time.monotonic()
        logger.info("tool=%s args=%s", name, args)
        try:
            tool = self.get(name)
        except ToolNotFound:
            self._log(name, started, "error", "not_found")
            raise
        try:
            _validate_args(tool.args_schema, args)
        except ArgsValidationError as exc:
            self._log(name, started, "error", f"args:{exc}")
            raise
        try:
            result = await tool.run(args, ctx)
        except ToolError as exc:
            self._log(name, started, "error", f"tool:{exc}")
            raise
        if not isinstance(result, str):
            result = str(result)
        out = truncate_output(result, MAX_TOOL_OUTPUT_CHARS)
        self._log(name, started, "ok")
        return out

    @staticmethod
    def _log(name: str, started: float, status: str, detail: str = "") -> None:
        dur_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "tool=%s dur_ms=%d status=%s%s",
            name,
            dur_ms,
            status,
            f" detail={detail}" if detail else "",
        )
