"""Tool `weather` — получение погоды через wttr.in.

См. `_skills/weather/SKILL.md` для подробностей.

Использует wttr.in без API-ключа через curl.
При ошибке сети или недоступности сервиса автоматически использует WebSearchTool для поиска погоды.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from app.tools.base import MAX_TOOL_OUTPUT_CHARS, Tool, ToolContext, truncate_output
from app.tools.errors import ToolError


class WeatherTool(Tool):
    name = "weather"
    description = (
        "Получает текущую погоду, прогноз, температуру и осадки для города/локации через wttr.in. "
        "Принимает параметр 'location' (город, регион или код аэропорта). "
        "При недоступности wttr.in автоматически использует веб-поиск для получения информации о погоде."
    )
    args_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Город, регион или код аэропорта (например: Moscow, New+York, SVO)",
            }
        },
        "required": ["location"],
    }

    def __init__(self, *, max_output_chars: int = MAX_TOOL_OUTPUT_CHARS) -> None:
        self._max_output_chars = max_output_chars

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        location = str(args["location"]).strip()
        if not location:
            raise ToolError("location is required")

        # Заменяем пробелы на + для URL
        location_url = location.replace(" ", "+")

        try:
            # Формируем команду curl для wttr.in
            # Используем формат 0 для подробных текущих условий
            cmd = ["curl", "-s", f"wttr.in/{location_url}?0"]
            
            # Запускаем команду
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore").strip()
                raise ToolError(f"curl failed: {error_msg}")

            result = stdout.decode("utf-8", errors="ignore")

            if not result or "Unknown location" in result:
                raise ToolError(f"Неизвестная локация: {location}")

            return truncate_output(result, self._max_output_chars)

        except FileNotFoundError:
            # curl не установлен - используем веб-поиск
            return await self._fallback_to_web_search(location, ctx)
        except asyncio.TimeoutError:
            # Таймаут - используем веб-поиск
            return await self._fallback_to_web_search(location, ctx)
        except ToolError as exc:
            # Если это ошибка wttr.in (неизвестная локация) - пробрасываем
            if "Неизвестная локация" in str(exc):
                raise
            # Другие ошибки сети - используем веб-поиск
            return await self._fallback_to_web_search(location, ctx)
        except Exception as exc:
            # При любой другой ошибке используем веб-поиск
            return await self._fallback_to_web_search(location, ctx)

    async def _fallback_to_web_search(self, location: str, ctx: ToolContext) -> str:
        """Fallback на WebSearchTool если wttr.in недоступен."""
        try:
            # Проверяем что WebSearchTool доступен в контексте
            if ctx.tools is None:
                raise ToolError(
                    f"Сервис wttr.in недоступен для локации {location}. "
                    f"WebSearchTool не доступен в контексте."
                )
            
            # Вызываем WebSearchTool для поиска погоды
            web_search_tool = ctx.tools.get("web_search")
            if web_search_tool is None:
                raise ToolError(
                    f"Сервис wttr.in недоступен для локации {location}. "
                    f"WebSearchTool не найден в реестре инструментов."
                )
            
            # Формируем запрос для поиска погоды
            search_query = f"погода {location}"
            search_args = {"query": search_query}
            
            search_result = await web_search_tool.run(search_args, ctx)
            
            return truncate_output(
                f"[Поиск в веб] Погода для {location}:\n{search_result}",
                self._max_output_chars
            )
        except Exception as exc:
            # Если и веб-поиск не сработал, возвращаем ошибку
            raise ToolError(
                f"Не удалось получить погоду для {location}. "
                f"Сервис wttr.in недоступен и веб-поиск также не удался: {exc}"
            ) from exc
