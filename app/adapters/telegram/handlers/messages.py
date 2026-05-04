"""Handler произвольного текста и документов: запуск агентного цикла.

См. `_docs/commands.md` § «Произвольный текст», `_docs/architecture.md` §4.

Поток:

1. Пустой/нетекстовый ввод → подсказка «В MVP я понимаю только текст».
2. Слишком длинный ввод (> `MAX_INPUT_LENGTH`) → подсказка, без обращения к LLM.
3. Сообщение пишется в `ConversationStore`, дальше вызывается
   `core.handle_user_task(...)` (адаптер не знает про executor напрямую).
4. Ошибки LLM-слоя превращаются в человекочитаемые ответы.
5. Ответ ассистента дописывается в `ConversationStore`.
6. При `len(history) >= history_summary_threshold` запускается in-session
   суммаризация; её падение — `WARNING`, ответ пользователю не страдает.
7. Длинный ответ (> 4096 символов) разбивается на несколько сообщений
   (Telegram-лимит).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from app.adapters.telegram.files import FileTooLargeError, download_telegram_file
from app.adapters.telegram.utils import format_for_telegram
from app.core.orchestrator import handle_user_task
from app.services.llm import LLMBadResponse, LLMTimeout, LLMUnavailable
from app.services.transcribe import (
    Transcriber,
    TranscriberUnavailableError,
    is_transcriber_available,
)
from app.services.vision import Vision
from app.utils.text import split_long_message

if TYPE_CHECKING:
    from app.agents.executor import Executor
    from app.config import Settings
    from app.services.conversation import ConversationStore
    from app.services.llm import OllamaClient
    from app.services.memory import SemanticMemory
    from app.services.model_registry import UserSettingsRegistry
    from app.services.summarizer import Summarizer

logger = logging.getLogger(__name__)

MAX_INPUT_LENGTH = 4000
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


async def _send_with_fallback(message: Message, text: str, parse_mode) -> None:
    """Отправить сообщение с fallback на ParseMode.NONE при ошибке парсинга."""
    try:
        await message.answer(text, parse_mode=parse_mode)
    except TelegramBadRequest:
        logger.warning("Ошибка парсинга Telegram, fallback на ParseMode.NONE")
        await message.answer(text, parse_mode=None)

NON_TEXT_REPLY = "В MVP я понимаю только текст."
TOO_LONG_INPUT_REPLY = "Слишком длинный запрос, сократите формулировку."
FILE_TOO_LARGE_REPLY = "Файл слишком большой, отправьте файл меньшего размера."
VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY = (
    "Распознавание речи недоступно, установите faster-whisper."
)
VISION_UNAVAILABLE_REPLY = "Vision-модель не подключена, отправь текстом, что на картинке."
LLM_UNAVAILABLE_REPLY = "LLM сейчас недоступна, попробуйте позже."
LLM_TIMEOUT_REPLY = "Модель слишком долго отвечает, попробуйте ещё раз."
LLM_BAD_RESPONSE_REPLY = (
    "Модель ответила в неожиданном формате, попробуйте ещё раз."
)
GENERIC_ERROR_REPLY = "Что-то пошло не так, попробуйте ещё раз."


def build_text_handler(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Callable[[Message], Awaitable[None]]:
    """Собрать async-handler для текстовых сообщений (без `/`-команд)."""

    async def handle_text(message: Message) -> None:
        text = message.text
        if not text:
            formatted, parse_mode = format_for_telegram(NON_TEXT_REPLY)
            await _send_with_fallback(message, formatted, parse_mode)
            return

        if message.from_user is None:
            # Технически возможно для каналов; в нашем MVP — игнорируем.
            return
        user_id = message.from_user.id
        chat_id = message.chat.id if message.chat is not None else user_id

        if len(text) > MAX_INPUT_LENGTH:
            formatted, parse_mode = format_for_telegram(TOO_LONG_INPUT_REPLY)
            await _send_with_fallback(message, formatted, parse_mode)
            return

        # Если это ответ на сообщение, добавляем контекст оригинала
        reply_msg = getattr(message, "reply_to_message", None)
        if reply_msg is not None:
            reply_text = getattr(reply_msg, "text", None) or getattr(reply_msg, "caption", None) or ""
            if reply_text:
                # Обрезаем длинный контекст до 500 символов
                if len(reply_text) > 500:
                    reply_text = reply_text[:500] + "..."
                text = f"[В ответ на: {reply_text}]\n{text}"
            # Если ответ на файл (фото, документ или голосовой), добавляем контекст конкретного файла по message_id
            if getattr(reply_msg, "photo", None) is not None or getattr(reply_msg, "document", None) is not None or getattr(reply_msg, "voice", None) is not None:
                reply_msg_id = getattr(reply_msg, "message_id", None)
                logger.info("reply на файл user=%s reply_msg_id=%s", user_id, reply_msg_id)
                if reply_msg_id is not None:
                    file_context = conversations.get_file_context(user_id, reply_msg_id)
                    logger.info("file_context найден=%s для reply_msg_id=%s", file_context is not None, reply_msg_id)
                    if file_context:
                        # Добавляем контекст конкретного файла
                        text = f"{file_context}\n\n{text}"
                    else:
                        logger.warning("контекст файла не найден для reply_msg_id=%s", reply_msg_id)

        conversations.add_user_message(user_id, text)
        model = user_settings.get_model(user_id)

        try:
            reply = await handle_user_task(
                text,
                user_id=user_id,
                chat_id=chat_id,
                conversations=conversations,
                executor=executor,
                model=model,
                settings=settings,
                llm=llm,
                semantic_memory=semantic_memory,
            )
        except LLMTimeout:
            logger.warning("LLM timeout user=%s", user_id)
            formatted, parse_mode = format_for_telegram(LLM_TIMEOUT_REPLY)
            await _send_with_fallback(message, formatted, parse_mode)
            return
        except LLMUnavailable:
            logger.error("LLM недоступна user=%s", user_id)
            formatted, parse_mode = format_for_telegram(LLM_UNAVAILABLE_REPLY)
            await _send_with_fallback(message, formatted, parse_mode)
            return
        except LLMBadResponse as exc:
            logger.warning("LLM вернула некорректный ответ user=%s error=%s", user_id, exc)
            # Если пустой ответ - это может быть из-за слишком большого контекста
            if "empty" in str(exc):
                error_msg = "Модель не смогла обработать такой большой запрос. Попробуйте отправить файл меньшего размера или задайте более конкретный вопрос."
            else:
                error_msg = f"Модель ответила в неожиданном формате: {exc}. Попробуйте ещё раз."
            formatted, parse_mode = format_for_telegram(error_msg)
            await _send_with_fallback(message, formatted, parse_mode)
            return

        conversations.add_assistant_message(user_id, reply)

        history = conversations.get_history(user_id)
        if len(history) >= settings.history_summary_threshold:
            try:
                summary = await summarizer.summarize(
                    history[:-2], model=model
                )
                conversations.replace_with_summary(
                    user_id, summary, kept_tail=2
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "in-session суммаризация не удалась user=%s",
                    user_id,
                    exc_info=True,
                )

        for part in split_long_message(reply, TELEGRAM_MAX_MESSAGE_LENGTH):
            formatted, parse_mode = format_for_telegram(part)
            await _send_with_fallback(message, formatted, parse_mode)

    return handle_text


async def handle_document(
    message: Message,
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> None:
    """Обработчик документов (PDF, TXT, MD)."""
    if message.from_user is None or message.document is None:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat is not None else user_id
    document = message.document
    caption = message.caption or ""

    # Скачиваем файл
    try:
        file_path = await download_telegram_file(
            message.bot,
            document.file_id,
            max_size_mb=settings.telegram_max_file_mb,
            tmp_dir=settings.tmp_base_dir,
            user_id=user_id,
            mime_type=document.mime_type,
        )
    except FileTooLargeError as exc:
        logger.warning("файл слишком большой user=%s size=%d", user_id, exc.file_size_mb)
        formatted, parse_mode = format_for_telegram(FILE_TOO_LARGE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except Exception as exc:
        logger.error("ошибка загрузки файла user=%s: %s", user_id, exc)
        formatted, parse_mode = format_for_telegram(GENERIC_ERROR_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Формируем обогащённый goal
    goal = f"Пользователь прислал документ {file_path}. Caption: {caption}. Прочитай через read_document и ответь по сути. Важно: для read_document используй ТОЛЬКО путь {file_path} без изменений, не меняй его и не используй относительные пути."

    conversations.add_user_message(user_id, goal)
    # Сохраняем контекст файла по message_id для ответов на конкретный файл
    conversations.save_file_context(user_id, message.message_id, "document", goal)
    model = user_settings.get_model(user_id)

    try:
        reply = await handle_user_task(
            goal,
            user_id=user_id,
            chat_id=chat_id,
            conversations=conversations,
            executor=executor,
            model=model,
            settings=settings,
            llm=llm,
            semantic_memory=semantic_memory,
        )
    except LLMTimeout:
        logger.warning("LLM timeout user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_TIMEOUT_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMUnavailable:
        logger.error("LLM недоступна user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMBadResponse:
        logger.warning("LLM вернула некорректный ответ user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_BAD_RESPONSE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    conversations.add_assistant_message(user_id, reply)

    history = conversations.get_history(user_id)
    if len(history) >= settings.history_summary_threshold:
        try:
            summary = await summarizer.summarize(history[:-2], model=model)
            conversations.replace_with_summary(user_id, summary, kept_tail=2)
        except Exception:  # noqa: BLE001
            logger.warning("in-session суммаризация не удалась user=%s", user_id, exc_info=True)

    for part in split_long_message(reply, TELEGRAM_MAX_MESSAGE_LENGTH):
        formatted, parse_mode = format_for_telegram(part)
        await _send_with_fallback(message, formatted, parse_mode)

    # Файл не удаляем сразу - он живёт до /new или TTL cleanup (как и изображения)


async def handle_voice(
    message: Message,
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> None:
    """Обработчик голосовых сообщений (Voice/Audio)."""
    if message.from_user is None or message.voice is None:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat is not None else user_id
    voice = message.voice

    # Проверяем доступность transcriber
    if not is_transcriber_available():
        logger.warning("transcriber недоступен user=%s", user_id)
        formatted, parse_mode = format_for_telegram(VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Скачиваем файл
    try:
        file_path = await download_telegram_file(
            message.bot,
            voice.file_id,
            max_size_mb=settings.telegram_max_file_mb,
            tmp_dir=settings.tmp_base_dir,
            user_id=user_id,
            mime_type=voice.mime_type,
        )
    except FileTooLargeError as exc:
        logger.warning("голосовое слишком большое user=%s size=%d", user_id, exc.file_size_mb)
        formatted, parse_mode = format_for_telegram(FILE_TOO_LARGE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except Exception as exc:
        logger.error("ошибка загрузки файла user=%s: %s", user_id, exc)
        formatted, parse_mode = format_for_telegram(GENERIC_ERROR_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Транскрибируем
    try:
        transcriber = Transcriber(
            model=settings.whisper_model, language=settings.whisper_language
        )
        text = transcriber.transcribe(file_path)
    except TranscriberUnavailableError:
        logger.warning("transcriber: инициализация не удалась user=%s", user_id)
        formatted, parse_mode = format_for_telegram(VOICE_TRANSCRIPTION_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except Exception as exc:
        logger.error("transcribe: ошибка распознавания user=%s: %s", user_id, exc)
        formatted, parse_mode = format_for_telegram(GENERIC_ERROR_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Если транскрипция пуста
    if not text:
        formatted, parse_mode = format_for_telegram("Не удалось распознать речь.")
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Формируем обогащённый goal с путём к файлу и транскрипцией
    goal = f"Голосовое сообщение: {file_path}\nТранскрипция: {text}"
    
    # Передаём goal в историю и для обработки
    conversations.add_user_message(user_id, goal)
    # Сохраняем контекст голосового файла по message_id для ответов на конкретный файл
    conversations.save_file_context(user_id, message.message_id, "voice", goal)
    model = user_settings.get_model(user_id)

    try:
        reply = await handle_user_task(
            goal,
            user_id=user_id,
            chat_id=chat_id,
            conversations=conversations,
            executor=executor,
            model=model,
            settings=settings,
            llm=llm,
            semantic_memory=semantic_memory,
        )
    except LLMTimeout:
        logger.warning("LLM timeout user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_TIMEOUT_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMUnavailable:
        logger.error("LLM недоступна user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMBadResponse:
        logger.warning("LLM вернула некорректный ответ user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_BAD_RESPONSE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    conversations.add_assistant_message(user_id, reply)

    history = conversations.get_history(user_id)
    if len(history) >= settings.history_summary_threshold:
        try:
            summary = await summarizer.summarize(history[:-2], model=model)
            conversations.replace_with_summary(user_id, summary, kept_tail=2)
        except Exception:  # noqa: BLE001
            logger.warning("in-session суммаризация не удалась user=%s", user_id, exc_info=True)

    for part in split_long_message(reply, TELEGRAM_MAX_MESSAGE_LENGTH):
        formatted, parse_mode = format_for_telegram(part)
        await _send_with_fallback(message, formatted, parse_mode)


async def handle_photo(
    message: Message,
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> None:
    """Обработчик фотографий (vision)."""
    if message.from_user is None or message.photo is None:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat is not None else user_id
    photo = message.photo[-1]  # Берём последнее (самое большое) фото
    caption = message.caption or ""

    # Проверяем доступность vision-модели
    if not settings.vision_model:
        logger.warning("vision-модель не настроена user=%s", user_id)
        formatted, parse_mode = format_for_telegram(VISION_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    if llm is None:
        logger.warning("LLM недоступна для vision user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Скачиваем файл
    try:
        file_path = await download_telegram_file(
            message.bot,
            photo.file_id,
            max_size_mb=settings.telegram_max_file_mb,
            tmp_dir=settings.tmp_base_dir,
            user_id=user_id,
            mime_type="image/jpeg",  # Telegram photos всегда JPEG
        )
    except FileTooLargeError as exc:
        logger.warning("фото слишком большое user=%s size=%d", user_id, exc.file_size_mb)
        formatted, parse_mode = format_for_telegram(FILE_TOO_LARGE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except Exception as exc:
        logger.error("ошибка загрузки файла user=%s: %s", user_id, exc)
        formatted, parse_mode = format_for_telegram(GENERIC_ERROR_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    # Описываем изображение
    try:
        vision = Vision(ollama=llm, model=settings.vision_model)
        description = await vision.describe(file_path, caption=caption)
    except Exception as exc:
        logger.error("vision: описание не удалось user=%s: %s", user_id, exc)
        formatted, parse_mode = format_for_telegram(GENERIC_ERROR_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        # Удаляем файл при ошибке
        try:
            file_path.unlink()
        except Exception:  # noqa: BLE001
            logger.warning("не удалось удалить временный photo-файл %s", file_path)
        return

    # Если описание пусто
    if not description:
        formatted, parse_mode = format_for_telegram("Не удалось описать изображение.")
        await _send_with_fallback(message, formatted, parse_mode)
        # Удаляем файл при ошибке
        try:
            file_path.unlink()
        except Exception:  # noqa: BLE001
            logger.warning("не удалось удалить временный photo-файл %s", file_path)
        return

    # Передаём описание с путём к файлу для уточняющих вопросов
    # Файл не удаляем сразу - он живёт до /new или TTL cleanup
    goal = f"Изображение: {file_path}\nОписание: {description}"
    conversations.add_user_message(user_id, goal)
    # Сохраняем контекст файла по message_id для ответов на конкретный файл
    conversations.save_file_context(user_id, message.message_id, "image", goal)
    model = user_settings.get_model(user_id)

    try:
        reply = await handle_user_task(
            goal,
            user_id=user_id,
            chat_id=chat_id,
            conversations=conversations,
            executor=executor,
            model=model,
            settings=settings,
            llm=llm,
            semantic_memory=semantic_memory,
        )
    except LLMTimeout:
        logger.warning("LLM timeout user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_TIMEOUT_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMUnavailable:
        logger.error("LLM недоступна user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_UNAVAILABLE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return
    except LLMBadResponse:
        logger.warning("LLM вернула некорректный ответ user=%s", user_id)
        formatted, parse_mode = format_for_telegram(LLM_BAD_RESPONSE_REPLY)
        await _send_with_fallback(message, formatted, parse_mode)
        return

    conversations.add_assistant_message(user_id, reply)

    history = conversations.get_history(user_id)
    if len(history) >= settings.history_summary_threshold:
        try:
            summary = await summarizer.summarize(history[:-2], model=model)
            conversations.replace_with_summary(user_id, summary, kept_tail=2)
        except Exception:  # noqa: BLE001
            logger.warning("in-session суммаризация не удалась user=%s", user_id, exc_info=True)

    for part in split_long_message(reply, TELEGRAM_MAX_MESSAGE_LENGTH):
        formatted, parse_mode = format_for_telegram(part)
        await _send_with_fallback(message, formatted, parse_mode)


def build_document_handler(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Callable[[Message], Awaitable[None]]:
    """Собрать async-handler для документов."""

    async def handler(message: Message) -> None:
        await handle_document(
            message,
            settings=settings,
            user_settings=user_settings,
            conversations=conversations,
            summarizer=summarizer,
            executor=executor,
            llm=llm,
            semantic_memory=semantic_memory,
        )

    return handler


def build_voice_handler(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Callable[[Message], Awaitable[None]]:
    """Собрать async-handler для голосовых сообщений."""

    async def handler(message: Message) -> None:
        await handle_voice(
            message,
            settings=settings,
            user_settings=user_settings,
            conversations=conversations,
            summarizer=summarizer,
            executor=executor,
            llm=llm,
            semantic_memory=semantic_memory,
        )

    return handler


def build_photo_handler(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Callable[[Message], Awaitable[None]]:
    """Собрать async-handler для фотографий."""

    async def handler(message: Message) -> None:
        await handle_photo(
            message,
            settings=settings,
            user_settings=user_settings,
            conversations=conversations,
            summarizer=summarizer,
            executor=executor,
            llm=llm,
            semantic_memory=semantic_memory,
        )

    return handler


def build_messages_router(
    *,
    settings: "Settings",
    user_settings: "UserSettingsRegistry",
    conversations: "ConversationStore",
    summarizer: "Summarizer",
    executor: "Executor",
    llm: "OllamaClient | None" = None,
    semantic_memory: "SemanticMemory | None" = None,
) -> Router:
    """Собрать aiogram-Router для произвольных текстовых сообщений и документов."""

    text_handler = build_text_handler(
        settings=settings,
        user_settings=user_settings,
        conversations=conversations,
        summarizer=summarizer,
        executor=executor,
        llm=llm,
        semantic_memory=semantic_memory,
    )

    document_handler = build_document_handler(
        settings=settings,
        user_settings=user_settings,
        conversations=conversations,
        summarizer=summarizer,
        executor=executor,
        llm=llm,
        semantic_memory=semantic_memory,
    )

    voice_handler = build_voice_handler(
        settings=settings,
        user_settings=user_settings,
        conversations=conversations,
        summarizer=summarizer,
        executor=executor,
        llm=llm,
        semantic_memory=semantic_memory,
    )

    photo_handler = build_photo_handler(
        settings=settings,
        user_settings=user_settings,
        conversations=conversations,
        summarizer=summarizer,
        executor=executor,
        llm=llm,
        semantic_memory=semantic_memory,
    )

    router = Router(name="messages")
    router.message.register(text_handler, lambda m: m.text is not None and not m.text.startswith("/"))
    router.message.register(document_handler, lambda m: m.document is not None)
    router.message.register(voice_handler, lambda m: m.voice is not None)
    router.message.register(photo_handler, lambda m: m.photo is not None)
    return router
