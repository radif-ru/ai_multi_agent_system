# План разработки (Roadmap)

Этапы проекта от пустого репозитория до зрелой мульти-агентной платформы. Каждый этап завершается зелёным `pytest`, ручной smoke-проверкой и закрытием соответствующего спринта (`_board/sprints/<NN>-<short-name>.md`).

## Этап 0. Bootstrap (текущий, Спринт 00)

- [ ] Документация (`_docs/` — все 17 файлов).
- [ ] Доска (`_board/`: `README.md`, `plan.md`, `process.md`, `progress.txt`, `sprints/00-bootstrap.md`, `sprints/01-mvp-agent.md`).
- [ ] Скелет каталогов: пустые пакеты `app/`, `tests/`, заготовки `_skills/`, `_prompts/`.
- [ ] Корневые файлы: `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, `README.md`.
- [ ] Системный промпт MVP (`_prompts/agent_system.md`) и промпт суммаризации (`_prompts/summarizer.md`) — наполнены.
- [ ] Один пример скилла в `_skills/example-summary/SKILL.md`.

**Готово когда:** структура соответствует `_docs/project-structure.md`, `pip install -r requirements.txt` отрабатывает, `python -c "import app"` не падает, документация перекрёстно ссылается без битых ссылок.

## Этап 1. MVP Agent (Спринт 01)

Запускаемый Telegram-бот с агентным циклом, базовыми tools, краткосрочной и долгосрочной памятью, командой `/new`. См. подробный план в `_board/sprints/01-mvp-agent.md`.

### Подэтапы

- **1.1** Конфиг + логирование (`app/config.py`, `app/logging_config.py`, тесты).
- **1.2** LLM-клиент (`app/services/llm.py` с `chat` + `embed`, иерархия ошибок, тесты).
- **1.3** Краткосрочная память (`app/services/conversation.py`, `app/services/summarizer.py`, тесты).
- **1.4** Парсер JSON (`app/agents/protocol.py`, тесты с граничными случаями).
- **1.5** Реестр tools и базовые tools (`registry`, `calculator`, `read_file`, `http_request`, `web_search`, `load_skill`, тесты).
- **1.6** Долгосрочная память (`app/services/memory.py` с `sqlite-vec`, `app/services/archiver.py`, tool `memory_search`, тесты).
- **1.7** Skills + Prompts (`SkillRegistry`, `PromptLoader`, инжекция в системный промпт, тесты).
- **1.8** Агентный цикл (`app/agents/executor.py`, тесты с моками).
- **1.9** Core / Telegram-адаптер (`core/orchestrator.py`, handlers, middleware, errors, тесты).
- **1.10** Полировка: README, чек-лист приёмки, smoke-проверка в реальном Telegram.

**Готово когда:** все пункты `_docs/mvp.md` §5 «Критерии приёмки» закрыты.

## Этап 2. Stream-индикация шагов агента

Сейчас пользователь видит только финальный ответ, а в промежутке — индикатор «печатает…». Для долгих циклов (5+ шагов) это слабая обратная связь.

- [ ] Edit-сообщение в Telegram: `Шаг 1: <thought>… Шаг 2: <thought>…`
- [ ] При финальном ответе — заменить шаги полным результатом.
- [ ] Лимит длины edit-сообщения (≤ 4096); при переполнении — отдельное сообщение.

**Когда:** после Спринта 01, отдельным спринтом «UX: streaming steps».

## Этап 3. Стриминг ответа Ollama

`OllamaClient.chat` сейчас вызывается с `stream=False`. Включение стриминга позволит показывать частичный `final_answer` сразу, пока он генерируется.

- [ ] `chat_stream` метод в `OllamaClient`.
- [ ] Адаптация Executor: при `final_answer`-шаге — стриминг в Telegram.
- [ ] При `action`-шаге — собираем полный ответ, парсим JSON.

**Когда:** опционально, после Этапа 2.

## Этап 4. Multi-agent (Planner + Critic)

Сейчас в коде есть только один агент — Executor. Для сложных задач нужны:

- [ ] **Planner** (`app/agents/planner.py`): получает задачу, возвращает DAG шагов или линейный план.
- [ ] **Critic** (`app/agents/critic.py`): получает draft-ответ Executor, возвращает `PASS|REVISE` + feedback.
- [ ] Расширение `core/orchestrator.py`: `task → planner → executor (per-step) → [critic → revise]* → final`.
- [ ] Режимы рефлексии: `OFF | NORMAL | DEEP` (выбор глубины ревизии: без неё, один проход, итеративно).
- [ ] Промпты: `_prompts/planner.md`, `_prompts/critic.md`.
- [ ] Capability graph: переиспользование результатов узлов через `{{nodeId}}` в инструкциях.
- [ ] Тесты: «Planner возвращает валидный DAG», «Critic возвращает PASS на корректный ответ», «Critic триггерит REVISE».

**Когда:** отдельный крупный спринт после Этапа 1.

## Этап 5. Новые адаптеры (web, MAX)

Архитектурно адаптеры подключаются единым контрактом `core.handle_user_task(text, user_id, chat_id)` (см. `architecture.md` §7.4).

- [ ] **Web-адаптер**: FastAPI/aiohttp + simple HTML chat-страница, общается с `core` напрямую (тот же event loop).
- [ ] **MAX-адаптер**: интеграция с мессенджером MAX (после изучения их API).
- [ ] Унифицированный `user_id` cross-channel (например, через таблицу `external_id → internal_user_id`).

**Когда:** после стабилизации MVP и Этапов 2–4.

## Этап 6. Webhook вместо polling

CON-4 запрещает webhook в MVP, но это кандидат на отдельный спринт.

- [ ] aiogram webhook server (aiohttp).
- [ ] Конфиг: `WEBHOOK_URL`, `WEBHOOK_SECRET`.
- [ ] TLS-настройка (через nginx или встроенный — на усмотрение).
- [ ] Совместимая работа: можно стартануть либо в polling, либо в webhook через флаг `BOT_MODE=polling|webhook`.

**Когда:** когда понадобится несколько инстансов / serverless / общий публичный URL.

## Этап 7. Файловые входы (фото, аудио, документы)

Расширение Telegram-адаптера на нетекстовые типы сообщений. Частично закрывается Спринтом 02 «Память и файловые входы» (`_board/sprints/02-memory-and-files.md` Этап 3).

- [ ] Обработчик `Photo`-сообщений: vision-модель (`qwen3-vl` или аналог через Ollama) → текст-описание → в агентный цикл. (Спринт 02, задача 3.5)
- [ ] Обработчик `Voice`/`Audio`: ffmpeg → Whisper (через Ollama, если поддерживается, иначе `faster-whisper`) → текст → в агентный цикл. (Спринт 02, задача 3.4)
- [ ] Обработчик `Document`: PDF/text → текстовое содержимое → в RAG. (Спринт 02, задачи 3.1–3.3)
- [ ] Лимит размера файла, лимит частоты. (Спринт 02, задача 3.1; throttling — Этап 9)

**Когда:** Спринт 02 берёт базовый объём; OCR PDF, видео, location и пр. — на отдельный спринт по запросу.

## Этап 8. Скиллы для практических задач

После того, как `_skills/` инфраструктура работает, наполняем библиотеку.

- [ ] `web_research` — пошаговый рисёрч с гибридной стратегией (поиск → отбор источников → извлечение → синтез).
- [ ] `code_review` — обзор кода с критериями.
- [ ] `russian_style` — корректировка под deliberate-стиль (без воды, конкретно).
- [ ] `email_draft`, `summary_long_text`, `tutorial_step_by_step` и пр.

**Когда:** инкрементально, по запросам пользователей.

## Этап 9. Throttling middleware

Защита от спама / лавинообразных запросов.

- [ ] Простой leaky-bucket по `user_id`: максимум N сообщений в M секунд.
- [ ] Параметры в `.env` (`THROTTLE_MAX_PER_MINUTE`).
- [ ] При превышении — мягкий ответ «слишком часто», без блокировки.

**Когда:** опционально, после смога эксплуатации.

## Этап 10. Docker / docker-compose

- [ ] `Dockerfile` для бота (multi-stage build: deps + runtime).
- [ ] `docker-compose.yml`: контейнер бота + контейнер Ollama (с GPU-passthrough опционально).
- [ ] Volume для `data/` (sqlite-vec БД переживает рестарт контейнера).
- [ ] `Makefile` (или `justfile`) с командами `make up`, `make down`, `make logs`.

**Когда:** опционально, при необходимости деплоя на чужую машину.

## Этап 11. CI

- [ ] `.github/workflows/test.yml`: setup-python + `pip install -r requirements.txt` + `pytest -q`.
- [ ] Линтер ruff в CI (ошибка → red).
- [ ] Бейдж в `README.md`.

**Когда:** после стабилизации тестов; перед публикацией репо публично.

## Этап 12. Sandboxed tools

Для tools, которые опасно запускать без изоляции (shell, произвольное чтение/запись ФС, sql-execute).

- [ ] `app/tools/sandboxed/` со своим контрактом `SandboxedTool`.
- [ ] Изоляция через `subprocess` + `chroot` / `firejail` / `podman` (на усмотрение).
- [ ] Whitelist команд / путей — конфигурируется через `.env`.

**Когда:** когда понадобится shell-tool или подобное (роадмап-кандидат, не приоритет).

## Этап 13. Точный токенайзер

Сейчас `estimate_tokens = chars / 4`. Для слабых моделей с маленьким окном это иногда неточно.

- [ ] `tiktoken` или HuggingFace tokenizer.
- [ ] Конфиг: `TOKENIZER_MODEL` (по умолчанию синхронизирован с LLM).
- [ ] Использовать в логах и в lint'ах перед `chat`-вызовом, чтобы предупреждать о переполнении контекста.

**Когда:** опционально, когда станет узким местом.

## Этап 14. Hot-reload скиллов и промптов

Сейчас правка `_skills/` и `_prompts/` требует рестарта процесса. Watcher на эти каталоги (через `watchdog`) автоматически перезагружает регистры.

- [ ] `SkillRegistry.watch(...)`.
- [ ] `PromptLoader.watch(...)`.

**Когда:** опционально, удобство разработки.

## Этап 15. Per-skill / per-task memory

Сейчас вся семантическая память — общий пул чанков. Расширения:

- [ ] Метка `skill_name` на чанках, фильтр по ней в `memory_search`.
- [ ] Краткое саммари каждой выполненной задачи (с tool calls + observations) для будущего Critic'а.

**Когда:** после Этапа 4.

## Ориентировочная последовательность

```
Этап 0 (Спринт 00)  → Этап 1 (Спринт 01)  → Этап 2 (UX)  → Этап 4 (multi-agent)
                                          ↘ Этап 8 (скиллы)
                                          ↘ Этап 9 (throttling)  ↘ Этап 11 (CI)
                                          ↘ Этап 10 (Docker)
                                                                  ↘ Этап 5 (web/MAX)
                                                                  ↘ Этап 6 (webhook)
```

Этапы 3, 7, 12, 13, 14, 15 — backlog по запросу пользователя.

## Принципы планирования

- Один активный спринт за раз (см. `_board/plan.md` § «Правила работы со спринтами», п.1).
- Новый спринт = новая ветка `feature/<short-name>`.
- Спринт оценивается в задачах, не в часах. Каждая задача проходит DoD из шаблона `_board/plan.md`.
- При обнаружении легаси / нюанса — записываем в `_docs/current-state.md` §2; не правим попутно.
