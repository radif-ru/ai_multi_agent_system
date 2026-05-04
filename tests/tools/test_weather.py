"""Тесты для WeatherTool."""

import pytest
from app.tools.weather import WeatherTool
from app.tools.errors import ToolError


@pytest.mark.asyncio
async def test_weather_tool_success() -> None:
    """Успешное получение погоды."""
    tool = WeatherTool()
    
    # Используем локацию, которая точно существует
    result = await tool.run({"location": "Moscow"}, ctx=None)
    
    # Проверяем, что результат не пустой
    assert result
    assert "Moscow" in result or "Москва" in result


@pytest.mark.asyncio
async def test_weather_tool_empty_location() -> None:
    """Пустая локация."""
    tool = WeatherTool()
    
    with pytest.raises(ToolError, match="location is required"):
        await tool.run({"location": ""}, ctx=None)


@pytest.mark.asyncio
async def test_weather_tool_no_location() -> None:
    """Нет параметра location."""
    tool = WeatherTool()
    
    with pytest.raises(KeyError):
        await tool.run({}, ctx=None)


@pytest.mark.asyncio
async def test_weather_tool_fallback_method_exists() -> None:
    """Проверка существования метода fallback."""
    tool = WeatherTool()
    # Проверяем, что метод fallback существует
    assert hasattr(tool, "_fallback_to_web_search")
