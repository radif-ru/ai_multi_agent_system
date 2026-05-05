"""Тесты консольного адаптера."""

import pytest
from app.adapters.console.adapter import ConsoleAdapter
from app.commands.context import CommandContext
from app.core.events import EventBus, MessageReceived, ResponseGenerated


@pytest.fixture
def mock_components():
    """Моки компонентов для тестов."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.history_summary_threshold = 10

    user_settings = MagicMock()
    user_settings.get_model.return_value = "qwen3.5:4b"
    user_settings.get_prompt.return_value = None

    prompts = MagicMock()
    prompts.agent_system_template = "test prompt"

    tools = MagicMock()
    tools.list_descriptions.return_value = [
        {"name": "calculator", "description": "калькулятор"}
    ]

    skills = MagicMock()
    skills.list_descriptions.return_value = [
        {"name": "bash-linux", "description": "bash команды"}
    ]

    conversations = MagicMock()
    conversations.get_session_log.return_value = []
    conversations.add_user_message = MagicMock()
    conversations.add_assistant_message = MagicMock()
    conversations.get_history.return_value = []

    archiver = MagicMock()

    core_handle_user_task = MagicMock(return_value="test response")

    users = MagicMock()

    event_bus = EventBus()
    # Регистрируем подписчиков для теста
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from functools import partial
    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=conversations))

    return {
        "settings": settings,
        "user_settings": user_settings,
        "prompts": prompts,
        "tools": tools,
        "skills": skills,
        "conversations": conversations,
        "archiver": archiver,
        "core_handle_user_task": core_handle_user_task,
        "users": users,
        "event_bus": event_bus,
    }


def test_console_adapter_init(mock_components):
    """Тест инициализации консольного адаптера."""
    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        **mock_components,
    )

    assert adapter.user_id == -1
    assert adapter.chat_id == -1
    assert adapter.settings == mock_components["settings"]
    assert adapter.user_settings == mock_components["user_settings"]


def test_console_adapter_build_context(mock_components):
    """Тест построения контекста."""
    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        **mock_components,
    )

    ctx = adapter._build_context()

    assert isinstance(ctx, CommandContext)
    assert ctx.user_id == -1
    assert ctx.chat_id == -1


@pytest.mark.asyncio
async def test_console_adapter_handle_command_start(mock_components):
    """Тест обработки команды /start."""
    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        **mock_components,
    )

    await adapter._handle_command("/start")

    # Проверяем, что команда выполнена (вывод в stdout)
    # В реальном тесте можно перехватить stdout


@pytest.mark.asyncio
async def test_console_adapter_handle_text(mock_components):
    """Тест обработки текстового сообщения."""
    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        **mock_components,
    )

    await adapter._handle_text("test message")

    # Проверяем, что core.handle_user_task вызван
    mock_components["core_handle_user_task"].assert_called_once()


@pytest.mark.asyncio
async def test_console_adapter_handle_command_exit(mock_components):
    """Тест обработки команды /exit."""
    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        **mock_components,
    )

    # Команда /exit должна прервать цикл, но в тесте мы проверяем только обработку
    # В реальном REPL это приведёт к break
    await adapter._handle_command("/exit")
