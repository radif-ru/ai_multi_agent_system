"""Точка входа приложения.

См. `_docs/architecture.md` §3.1. Сборка зависимостей и запуск polling
выделены в отдельные функции (`_build_components`, `_wire_telegram`,
`_start_polling`, `_shutdown`) — это упрощает unit-smoke-тест в
`tests/test_main.py`, который патчит `_start_polling`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.adapters.telegram.handlers.commands import build_commands_router
from app.adapters.telegram.handlers.errors import build_errors_router
from app.adapters.telegram.handlers.messages import build_messages_router
from app.agents.executor import Executor
from app.config import Settings
from app.core import orchestrator as _orchestrator  # импорт для DI/тестов
from app.logging_config import setup_logging
from app.middlewares.logging_mw import LoggingMiddleware
from app.services.archiver import Archiver
from app.services.conversation import ConversationStore
from app.services.llm import OllamaClient
from app.services.memory import MemoryUnavailable, SemanticMemory
from app.services.model_registry import UserSettingsRegistry
from app.services.prompts import PromptLoader
from app.services.skills import SkillRegistry
from app.services.summarizer import Summarizer
from app.tools.calculator import CalculatorTool
from app.tools.describe_image import DescribeImageTool
from app.tools.http_request import HttpRequestTool
from app.tools.load_skill import LoadSkillTool
from app.tools.memory_search import MemorySearchTool
from app.tools.read_document import ReadDocumentTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool
from app.tools.weather import WeatherTool
from app.users.repository import UserRepository
from app.core.events import EventBus, MessageReceived, ResponseGenerated

logger = logging.getLogger(__name__)

_BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="models", description="Список моделей"),
    BotCommand(command="model", description="Выбрать модель"),
    BotCommand(command="prompt", description="Задать системный промпт"),
    BotCommand(command="new", description="Архивировать и открыть новую сессию"),
    BotCommand(command="reset", description="Очистить контекст и сбросить настройки"),
]

assert _orchestrator is not None  # явная зависимость для будущего DI


@dataclass
class _Components:
    """Долгоживущие сервисы приложения."""

    settings: Settings
    llm: OllamaClient
    conversations: ConversationStore
    summarizer: Summarizer
    semantic_memory: SemanticMemory | None
    skills: SkillRegistry
    prompts: PromptLoader
    user_settings: UserSettingsRegistry
    tools: ToolRegistry
    archiver: Archiver
    executor: Executor
    users: UserRepository
    event_bus: EventBus


async def _build_components(settings: Settings) -> _Components:
    llm = OllamaClient(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout,
        num_ctx=settings.ollama_num_ctx,
    )
    conversations = ConversationStore(
        max_messages=settings.history_max_messages,
        session_log_max_messages=settings.session_log_max_messages,
    )
    summarizer = Summarizer(
        llm=llm,
        system_prompt=settings.summarization_prompt,
        chunk_messages=settings.summarizer_chunk_messages,
    )

    semantic_memory: SemanticMemory | None = SemanticMemory(
        db_path=settings.memory_db_path, dimensions=settings.embedding_dimensions
    )
    try:
        await semantic_memory.init()
    except MemoryUnavailable as exc:
        logger.error("долгосрочная память недоступна: %s", exc)
        semantic_memory = None

    skills = SkillRegistry("_skills")
    skills.load()
    prompts = PromptLoader(settings.agent_system_prompt_path)
    user_settings = UserSettingsRegistry(
        default_model=settings.ollama_default_model,
        default_search_engine=settings.search_engine_default,
    )

    tools = ToolRegistry(
        [
            CalculatorTool(),
            ReadFileTool(),
            ReadDocumentTool(
                tmp_files_dir=settings.tmp_base_dir,
                max_file_size_mb=settings.telegram_max_file_mb,
                max_extracted_images=settings.read_document_max_extracted_images,
                max_ocr_images=settings.read_document_max_ocr_images,
                ocr_enabled=settings.read_document_ocr_enabled
            ),
            HttpRequestTool(),
            WebSearchTool(),
            MemorySearchTool(),
            LoadSkillTool(),
            DescribeImageTool(tmp_dir=settings.tmp_base_dir),
            WeatherTool(),
        ]
    )
    archiver = Archiver(
        llm=llm,
        summarizer=summarizer,
        semantic_memory=semantic_memory,  # type: ignore[arg-type]
        summarizer_model=settings.ollama_default_model,
        embedding_model=settings.embedding_model,
        chunk_size=settings.memory_chunk_size,
        chunk_overlap=settings.memory_chunk_overlap,
        concurrency_limit=settings.embedding_concurrency,
    )
    executor = Executor(
        settings=settings,
        llm=llm,
        tools=tools,
        prompts=prompts,
        skills=skills,
        semantic_memory=semantic_memory,
        user_settings=user_settings,
        summarizer=summarizer,
    )
    event_bus = EventBus()
    users = UserRepository(event_bus=event_bus)

    # Регистрируем подписчиков для записи в ConversationStore
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from app.services.summarizer_subscriber import on_response_generated_summarize
    from functools import partial

    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=conversations))
    # Регистрируем подписчика суммаризации ПОСЛЕ conversation_subscriber, чтобы ответ уже был записан в стор
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated_summarize, conversations=conversations, summarizer=summarizer, user_settings=user_settings, settings=settings))

    return _Components(
        settings=settings,
        llm=llm,
        conversations=conversations,
        summarizer=summarizer,
        semantic_memory=semantic_memory,
        skills=skills,
        prompts=prompts,
        user_settings=user_settings,
        tools=tools,
        archiver=archiver,
        executor=executor,
        users=users,
        event_bus=event_bus,
    )


def _wire_telegram(c: _Components) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=c.settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher["users"] = c.users
    dispatcher["event_bus"] = c.event_bus
    dispatcher.update.middleware(LoggingMiddleware())
    dispatcher.include_router(
        build_commands_router(
            settings=c.settings,
            user_settings=c.user_settings,
            prompts=c.prompts,
            tools=c.tools,
            skills=c.skills,
            conversations=c.conversations,
            archiver=c.archiver,
            users=c.users,
        )
    )
    dispatcher.include_router(
        build_messages_router(
            settings=c.settings,
            user_settings=c.user_settings,
            conversations=c.conversations,
            summarizer=c.summarizer,
            executor=c.executor,
            llm=c.llm,
            semantic_memory=c.semantic_memory,
        )
    )
    dispatcher.include_router(build_errors_router())
    return bot, dispatcher


async def _start_polling(bot: Bot, dispatcher: Dispatcher) -> None:
    """Зарегистрировать команды у BotFather и запустить polling.

    Вынесено отдельной функцией, чтобы smoke-тест мог замокать всю
    сетевую часть одной точкой.
    """
    await bot.set_my_commands(_BOT_COMMANDS)
    await dispatcher.start_polling(bot)


async def _shutdown(bot: Bot, components: _Components) -> None:
    try:
        await bot.session.close()
    except Exception:  # noqa: BLE001
        logger.exception("ошибка при закрытии bot.session")
    try:
        await components.llm.close()
    except Exception:  # noqa: BLE001
        logger.exception("ошибка при закрытии llm-клиента")
    if components.semantic_memory is not None:
        try:
            await components.semantic_memory.close()
        except Exception:  # noqa: BLE001
            logger.exception("ошибка при закрытии семантической памяти")


async def main() -> None:
    """Async-точка входа: сборка, запуск polling, корректный shutdown."""
    settings = Settings()
    setup_logging(settings)

    components = await _build_components(settings)
    bot, dispatcher = _wire_telegram(components)
    try:
        logger.info("Bot started")
        await _start_polling(bot, dispatcher)
    finally:
        await _shutdown(bot, components)


def run() -> None:
    """Синхронный wrapper для `python -m app`."""
    asyncio.run(main())


if __name__ == "__main__":  # pragma: no cover
    run()
