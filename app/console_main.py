"""Точка входа консольного режима.

Запуск через `python -m app.console_main`.

См. `_docs/console-adapter.md`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.adapters.console.adapter import ConsoleAdapter
from app.agents.executor import Executor
from app.config import Settings
from app.core import orchestrator as _orchestrator
from app.logging_config import setup_logging
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

assert _orchestrator is not None  # явная зависимость для будущего DI


async def _build_components(settings: Settings) -> tuple:
    """Построить компоненты для консольного адаптера."""
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
    from app.services.summarizer_subscriber import on_response_generated_summarize
    from app.services.tmp_cleanup import on_conversation_archived_cleanup
    from functools import partial

    event_bus.subscribe(MessageReceived, partial(on_message_received, conversations=conversations))
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated, conversations=conversations))
    # Регистрируем подписчика суммаризации ПОСЛЕ conversation_subscriber, чтобы ответ уже был записан в стор
    event_bus.subscribe(ResponseGenerated, partial(on_response_generated_summarize, conversations=conversations, summarizer=summarizer, user_settings=user_settings, settings=settings))
    # Регистрируем подписчика очистки tmp-изображений при успешном архивировании
    event_bus.subscribe(ConversationArchived, partial(on_conversation_archived_cleanup, tmp_dir=Path(settings.tmp_base_dir)))

    return (
        settings,
        llm,
        conversations,
        summarizer,
        semantic_memory,
        skills,
        prompts,
        user_settings,
        tools,
        archiver,
        executor,
        users,
        event_bus,
    )


async def _shutdown(
    llm: OllamaClient,
    semantic_memory: SemanticMemory | None,
) -> None:
    """Корректно закрыть ресурсы."""
    try:
        await llm.close()
    except Exception:  # noqa: BLE001
        logger.exception("ошибка при закрытии llm-клиента")
    if semantic_memory is not None:
        try:
            await semantic_memory.close()
        except Exception:  # noqa: BLE001
            logger.exception("ошибка при закрытии семантической памяти")


async def main() -> None:
    """Async-точка входа консольного режима."""
    settings = Settings()
    # Отключаем консольный вывод логов чтобы не смешивать с ответами агента
    setup_logging(settings, console_output=False)

    (
        settings,
        llm,
        conversations,
        summarizer,
        semantic_memory,
        skills,
        prompts,
        user_settings,
        tools,
        archiver,
        executor,
        users,
        event_bus,
    ) = await _build_components(settings)

    # Функция core.handle_user_task для текстовых сообщений
    async def core_handle_user_task(
        *,
        text: str,
        user_id: int,
        chat_id: int,
        conversations: ConversationStore,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Обёртка над core.orchestrator.handle_user_task."""
        from app.core import orchestrator

        return await orchestrator.handle_user_task(
            text=text,
            user_id=user_id,
            chat_id=chat_id,
            conversations=conversations,
            executor=executor,
            model=model,
        )

    adapter = ConsoleAdapter(
        user_id=-1,
        chat_id=-1,
        settings=settings,
        user_settings=user_settings,
        prompts=prompts,
        tools=tools,
        skills=skills,
        conversations=conversations,
        archiver=archiver,
        core_handle_user_task=core_handle_user_task,
        users=users,
        event_bus=event_bus,
    )

    try:
        logger.info("Console adapter started")
        await adapter.run()
    finally:
        await _shutdown(llm, semantic_memory)


def run() -> None:
    """Синхронный wrapper для `python -m app.console_main`."""
    asyncio.run(main())


if __name__ == "__main__":  # pragma: no cover
    run()
