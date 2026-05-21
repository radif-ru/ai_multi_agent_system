"""Точка входа приложения.

См. `_docs/architecture.md` §3.1. Сборка зависимостей и запуск polling
выделены в отдельные функции (`_build_components`, `_wire_telegram`,
`_start_polling`, `_shutdown`) — это упрощает unit-smoke-тест в
`tests/test_main.py`, который патчит `_start_polling`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.adapters.telegram.handlers.commands import build_commands_router
from app.adapters.telegram.handlers.errors import build_errors_router
from app.adapters.telegram.handlers.messages import build_messages_router
from app.agents.critic import CriticAgent
from app.agents.executor import Executor
from app.agents.planner import PlannerAgent
from app.config import Settings
from app.core import orchestrator as _orchestrator  # импорт для DI/тестов
from app.core.logging_config import setup_logging
from app.observability import setup_sentry
from app.middlewares.logging_mw import LoggingMiddleware
from app.services.archiver import Archiver
from app.services.conversation import ConversationStore
from app.services.dialog_journal import DialogJournal
from app.services.journal_recovery import recover_pending_journals
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
from app.tools.ocr_image import OcrImageTool
from app.tools.read_document import ReadDocumentTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool
from app.tools.weather import WeatherTool
from app.users.repository import UserRepository
from app.core.events import EventBus, MessageReceived, ResponseGenerated
from app.security import get_global_mapper

# Monkey-patch aiohttp ClientSession для поддержки прокси через переменные окружения
_original_init = aiohttp.ClientSession.__init__


def patched_init(self, *args, **kwargs):
    # Если прокси настроен в переменных окружения, добавляем trust_env=True
    proxy_env = (
        os.environ.get("HTTP_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("https_proxy")
    )
    if proxy_env:
        kwargs.setdefault("trust_env", True)
    return _original_init(self, *args, **kwargs)


aiohttp.ClientSession.__init__ = patched_init

logger = logging.getLogger(__name__)

_BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="models", description="Список моделей"),
    BotCommand(command="model", description="Выбрать модель"),
    BotCommand(command="prompt", description="Задать системный промпт"),
    BotCommand(command="mode", description="Режим рефлексии (off/normal/deep)"),
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
    dialog_journal: DialogJournal | None
    skills: SkillRegistry
    prompts: PromptLoader
    user_settings: UserSettingsRegistry
    tools: ToolRegistry
    archiver: Archiver
    executor: Executor
    planner: PlannerAgent
    critic: CriticAgent
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
        journal_db_path=settings.memory_db_path,
    )
    prompts = PromptLoader(settings.agent_system_prompt_path)
    summarizer = Summarizer(
        llm=llm,
        system_prompt=prompts.summarizer_prompt,
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

    # Журнал диалога для восстановления при рестарте (спринт 06 §3)
    dialog_journal: DialogJournal | None = DialogJournal(
        db_path=settings.memory_db_path
    )
    try:
        await dialog_journal.init()
    except Exception as exc:  # noqa: BLE001
        logger.error("dialog_journal: инициализация не удалась, журнал выключен: %s", exc)
        dialog_journal = None

    # Инициализируем FileIdMapper для загрузки существующих маппингов
    try:
        get_global_mapper().init()
    except Exception as exc:  # noqa: BLE001
        logger.error("ошибка инициализации FileIdMapper: %s", exc)

    skills = SkillRegistry("app/skills")
    skills.load()
    user_settings = UserSettingsRegistry(
        default_model=settings.ollama_default_model,
        default_search_engine=settings.search_engine_default,
    )

    tools = ToolRegistry(
        [
            CalculatorTool(),
            ReadFileTool(max_output_chars=settings.max_tool_output_chars),
            ReadDocumentTool(
                tmp_files_dir=settings.tmp_base_dir,
                max_file_size_mb=settings.telegram_max_file_mb,
                max_document_chars=settings.max_document_chars,
                max_images=settings.document_max_images,
                ocr_enabled=settings.document_ocr_enabled,
                ocr_min_text_threshold=settings.ocr_min_text_threshold,
            ),
            HttpRequestTool(max_output_chars=settings.max_tool_output_chars),
            WebSearchTool(max_output_chars=settings.max_tool_output_chars),
            MemorySearchTool(max_output_chars=settings.max_tool_output_chars),
            LoadSkillTool(max_output_chars=settings.max_tool_output_chars),
            DescribeImageTool(tmp_dir=settings.tmp_base_dir),
            OcrImageTool(tmp_dir=settings.tmp_base_dir, max_output_chars=settings.max_tool_output_chars),
            WeatherTool(max_output_chars=settings.max_tool_output_chars),
        ],
        max_output_chars=settings.max_tool_output_chars
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
    planner = PlannerAgent(llm=llm, prompts=prompts, settings=settings)
    critic = CriticAgent(llm=llm, prompts=prompts, settings=settings)
    event_bus = EventBus()
    users = UserRepository(db_path=settings.memory_db_path, event_bus=event_bus)
    await users.init()
    archiver = Archiver(
        llm=llm,
        summarizer=summarizer,
        semantic_memory=semantic_memory,  # type: ignore[arg-type]
        summarizer_model=settings.ollama_default_model,
        embedding_model=settings.embedding_model,
        chunk_size=settings.memory_chunk_size,
        chunk_overlap=settings.memory_chunk_overlap,
        concurrency_limit=settings.embedding_concurrency,
        event_bus=event_bus,
    )

    # Регистрируем подписчиков для записи в ConversationStore
    from app.core.events import ConversationArchived
    from app.services.conversation_subscriber import on_message_received, on_response_generated
    from app.services.dialog_journal_subscriber import (
        on_message_received_journal, on_response_generated_journal,
    )
    from app.services.summarizer_subscriber import on_response_generated_summarize
    from app.services.tmp_cleanup import on_conversation_archived_cleanup
    from functools import partial

    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=conversations))
    # Подписчики dialog_journal — СНАЧАЛА ПОСЛЕ conversation_subscriber, чтобы
    # current_conversation_id() видел свежий cid после add_user_message
    if dialog_journal is not None:
        event_bus.subscribe(
            MessageReceived,
            partial(
                on_message_received_journal,
                conversations=conversations, journal=dialog_journal,
            ),
        )
        event_bus.subscribe(
            ResponseGenerated,
            partial(
                on_response_generated_journal,
                conversations=conversations, journal=dialog_journal,
            ),
        )
    # Регистрируем подписчика суммаризации ПОСЛЕ conversation_subscriber, чтобы ответ уже был записан в стор
    event_bus.subscribe(
        ResponseGenerated,
        partial(
            on_response_generated_summarize,
            conversations=conversations,
            summarizer=summarizer,
            user_settings=user_settings,
            settings=settings,
        ),
    )
    # Регистрируем подписчика очистки tmp-изображений при успешном архивировании
    event_bus.subscribe(
        ConversationArchived,
        partial(on_conversation_archived_cleanup, tmp_dir=Path(settings.tmp_base_dir)),
    )

    return _Components(
        settings=settings,
        llm=llm,
        conversations=conversations,
        summarizer=summarizer,
        semantic_memory=semantic_memory,
        dialog_journal=dialog_journal,
        skills=skills,
        prompts=prompts,
        user_settings=user_settings,
        tools=tools,
        archiver=archiver,
        executor=executor,
        planner=planner,
        critic=critic,
        users=users,
        event_bus=event_bus,
    )


def _wire_telegram(c: _Components) -> tuple[Bot, Dispatcher]:
    # Monkey-patch добавляет trust_env=True, также передаем proxy явно
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    bot = Bot(
        token=c.settings.telegram_bot_token,
        request_timeout=30,
        proxy=https_proxy or http_proxy,
    )
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
            journal=c.dialog_journal,
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
            planner=c.planner,
            critic=c.critic,
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
    if components.dialog_journal is not None:
        try:
            await components.dialog_journal.close()
        except Exception:  # noqa: BLE001
            logger.exception("ошибка при закрытии dialog_journal")
    try:
        await components.users.close()
    except Exception:  # noqa: BLE001
        logger.exception("ошибка при закрытии UserRepository")
    try:
        from app.security import get_global_mapper
        get_global_mapper().close()
    except Exception:  # noqa: BLE001
        logger.exception("ошибка при закрытии FileIdMapper")


async def main() -> None:
    """Async-точка входа: сборка, запуск polling, корректный shutdown."""
    settings = Settings()
    setup_logging(settings)
    setup_sentry(settings)

    # Graceful shutdown через сигналы SIGTERM/SIGINT
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Получен сигнал shutdown, останавливаем бота...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    if not settings.dangerous_tools_allowlist:
        logger.info(
            "DANGEROUS_TOOLS_ALLOWLIST пуст: опасные tools (http_request, read_file) "
            "запрещены (secure by default). Чтобы включить — задайте в .env, например: "
            "DANGEROUS_TOOLS_ALLOWLIST=http_request,read_file"
        )

    components = await _build_components(settings)
    bot, dispatcher = _wire_telegram(components)

    # Фоновое восстановление «висящих» сессий из dialog_journal.
    # Запускаем параллельно с polling, чтобы не блокировать старт бота
    # (см. _docs/memory.md §4 и _docs/architecture.md §3.1).
    recovery_task: asyncio.Task | None = None
    if components.dialog_journal is not None:
        recovery_task = asyncio.create_task(
            recover_pending_journals(
                journal=components.dialog_journal,
                archiver=components.archiver,
            ),
            name="journal_recovery",
        )

    try:
        logger.info("Bot started")
        # Запускаем polling в отдельной задаче для graceful shutdown по сигналу
        polling_task = asyncio.create_task(_start_polling(bot, dispatcher))
        await shutdown_event.wait()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    finally:
        if recovery_task is not None and not recovery_task.done():
            recovery_task.cancel()
            try:
                await recovery_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await _shutdown(bot, components)


def run() -> None:
    """Синхронный wrapper для `python -m app`."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception("необработанное исключение на верхнем уровне")
        raise


if __name__ == "__main__":  # pragma: no cover
    run()
