# План разработки (Roadmap)

Этапы проекта от пустого репозитория до зрелой мульти-агентной платформы. Каждый этап завершается зелёным `pytest`, ручной smoke-проверкой и закрытием соответствующего спринта (`_board/sprints/<NN>-<short-name>.md`).

## Роль документа

- **Roadmap** — стратегический список этапов: что планируем сделать в обозримом будущем, в каком порядке, какие зависимости между этапами. Источник кандидатов на новые спринты.
- **Не дублирует** `current-state.md` (фактическое состояние кода) и `_board/plan.md` (индекс активных/закрытых спринтов).
- **Когда правится** — см. `_board/process.md` §8.2.

Статусы этапов:

- `Closed` — этап закрыт соответствующим спринтом, чекбоксы внутри отмечены.
- `Active` — по этапу идёт активный спринт (см. `_board/plan.md`).
- `Planned` — этап запланирован, спринт ещё не открыт.
- `Backlog` — этап в очереди без жёстких сроков.

## Этап 1. Bootstrap

**Статус:** Closed (Спринт 00, 2026-04-28).

- [x] Документация (`_docs/` — все 17 файлов).
- [x] Доска (`_board/`: `README.md`, `plan.md`, `process.md`, `progress.txt`, `sprints/00-bootstrap.md`, `sprints/01-mvp-agent.md`).
- [x] Скелет каталогов: пустые пакеты `app/`, `tests/`, заготовки `_skills/`, `_prompts/`.
- [x] Корневые файлы: `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, `README.md`.
- [x] Системный промпт MVP (`_prompts/agent_system.md`) и промпт суммаризации (`_prompts/summarizer.md`) — наполнены.
- [x] Один пример скилла в `_skills/example-summary/SKILL.md`.

**Готово когда:** структура соответствует `_docs/project-structure.md`, `pip install -r requirements.txt` отрабатывает, `python -c "import app"` не падает, документация перекрёстно ссылается без битых ссылок.

## Этап 2. MVP Agent

**Статус:** Closed (Спринт 01, 2026-04-28).

Запускаемый Telegram-бот с агентным циклом, базовыми tools, краткосрочной и долгосрочной памятью, командой `/new`. См. `_board/sprints/01-mvp-agent.md`.

### Подэтапы

- **2.1** Конфиг + логирование (`app/config.py`, `app/logging_config.py`, тесты).
- **2.2** LLM-клиент (`app/services/llm.py` с `chat` + `embed`, иерархия ошибок, тесты).
- **2.3** Краткосрочная память (`app/services/conversation.py`, `app/services/summarizer.py`, тесты).
- **2.4** Парсер JSON (`app/agents/protocol.py`, тесты с граничными случаями).
- **2.5** Реестр tools и базовые tools (`registry`, `calculator`, `read_file`, `http_request`, `web_search`, `load_skill`, тесты).
- **2.6** Долгосрочная память (`app/services/memory.py` с `sqlite-vec`, `app/services/archiver.py`, tool `memory_search`, тесты).
- **2.7** Skills + Prompts (`SkillRegistry`, `PromptLoader`, инжекция в системный промпт, тесты).
- **2.8** Агентный цикл (`app/agents/executor.py`, тесты с моками).
- **2.9** Core / Telegram-адаптер (`core/orchestrator.py`, handlers, middleware, errors, тесты).
- **2.10** Полировка: README, чек-лист приёмки, smoke-проверка в реальном Telegram.

**Готово когда:** все пункты `_docs/mvp.md` §5 «Критерии приёмки» закрыты.

## Этап 3. Stream-индикация шагов агента

**Статус:** Backlog.

Сейчас пользователь видит только финальный ответ, а в промежутке — индикатор «печатает…». Для долгих циклов (5+ шагов) это слабая обратная связь.

- [ ] Edit-сообщение в Telegram: `Шаг 1: <thought>… Шаг 2: <thought>…`
- [ ] При финальном ответе — заменить шаги полным результатом.
- [ ] Лимит длины edit-сообщения (≤ 4096); при переполнении — отдельное сообщение.

**Когда:** отдельным спринтом «UX: streaming steps».

## Этап 4. Стриминг ответа Ollama

**Статус:** Backlog.

`OllamaClient.chat` сейчас вызывается с `stream=False`. Включение стриминга позволит показывать частичный `final_answer` сразу, пока он генерируется.

- [ ] `chat_stream` метод в `OllamaClient`.
- [ ] Адаптация Executor: при `final_answer`-шаге — стриминг в Telegram.
- [ ] При `action`-шаге — собираем полный ответ, парсим JSON.

**Когда:** опционально, после Этапа 3.

## Этап 5. Multi-agent (Planner + Critic)

**Статус:** Planned.

Сейчас в коде есть только один агент — Executor. Для сложных задач нужны:

- [ ] **Planner** (`app/agents/planner.py`): получает задачу, возвращает DAG шагов или линейный план.
- [ ] **Critic** (`app/agents/critic.py`): получает draft-ответ Executor, возвращает `PASS|REVISE` + feedback.
- [ ] Расширение `core/orchestrator.py`: `task → planner → executor (per-step) → [critic → revise]* → final`.
- [ ] Режимы рефлексии: `OFF | NORMAL | DEEP` (выбор глубины ревизии: без неё, один проход, итеративно).
- [ ] Промпты: `_prompts/planner.md`, `_prompts/critic.md`.
- [ ] Capability graph: переиспользование результатов узлов через `{{nodeId}}` в инструкциях.
- [ ] Тесты: «Planner возвращает валидный DAG», «Critic возвращает PASS на корректный ответ», «Critic триггерит REVISE».

**Когда:** отдельный крупный спринт после Этапа 2.

## Этап 6. Новые адаптеры (web, MAX)

**Статус:** Planned.

Архитектурно адаптеры подключаются единым контрактом `core.handle_user_task(text, user_id, chat_id)` (см. `architecture.md` §8.4).

- [ ] **Web-адаптер**: FastAPI/aiohttp + simple HTML chat-страница, общается с `core` напрямую (тот же event loop).
- [ ] **MAX-адаптер**: интеграция с мессенджером MAX (после изучения их API).
- [ ] Унифицированный `user_id` cross-channel (например, через таблицу `external_id → internal_user_id`).

**Когда:** после стабилизации MVP и Этапов 3–5.

## Этап 7. Webhook вместо polling

**Статус:** Backlog.

CON-4 запрещает webhook в MVP, но это кандидат на отдельный спринт.

- [ ] aiogram webhook server (aiohttp).
- [ ] Конфиг: `WEBHOOK_URL`, `WEBHOOK_SECRET`.
- [ ] TLS-настройка (через nginx или встроенный — на усмотрение).
- [ ] Совместимая работа: можно стартануть либо в polling, либо в webhook через флаг `BOT_MODE=polling|webhook`.

**Когда:** когда понадобится несколько инстансов / serverless / общий публичный URL.

## Этап 8. Файловые входы (фото, аудио, документы)

**Статус:** Closed (частично закрыт Спринтом 02 «Память и файловые входы», 2026-04-29; OCR PDF, видео, location — backlog).

- [x] Обработчик `Photo`-сообщений: vision-модель → текст-описание → в агентный цикл (Спринт 02, задача 3.5).
- [x] Обработчик `Voice`/`Audio`: ffmpeg → Whisper (`faster-whisper`) → текст → в агентный цикл (Спринт 02, задача 3.4).
- [x] Обработчик `Document`: PDF/text → текстовое содержимое → в RAG (Спринт 02, задачи 3.1–3.3).
- [x] Лимит размера файла (Спринт 02, задача 3.1; throttling — Этап 10).
- [ ] OCR PDF, видео, location — отдельный спринт по запросу.

## Этап 9. Скиллы для практических задач

**Статус:** Backlog (инкрементально).

После того, как `_skills/` инфраструктура работает, наполняем библиотеку.

- [ ] `web_research` — пошаговый рисёрч с гибридной стратегией (поиск → отбор источников → извлечение → синтез).
- [ ] `code_review` — обзор кода с критериями.
- [ ] `russian_style` — корректировка под deliberate-стиль (без воды, конкретно).
- [ ] `email_draft`, `summary_long_text`, `tutorial_step_by_step` и пр.

**Когда:** инкрементально, по запросам пользователей.

## Этап 10. Throttling middleware

**Статус:** Backlog.

Защита от спама / лавинообразных запросов.

- [ ] Простой leaky-bucket по `user_id`: максимум N сообщений в M секунд.
- [ ] Параметры в `.env` (`THROTTLE_MAX_PER_MINUTE`).
- [ ] При превышении — мягкий ответ «слишком часто», без блокировки.

**Когда:** опционально, после смога эксплуатации.

## Этап 11. Docker / docker-compose

**Статус:** Backlog.

- [ ] `Dockerfile` для бота (multi-stage build: deps + runtime).
- [ ] `docker-compose.yml`: контейнер бота + контейнер Ollama (с GPU-passthrough опционально).
- [ ] Volume для `data/` (sqlite-vec БД переживает рестарт контейнера).
- [ ] `Makefile` (или `justfile`) с командами `make up`, `make down`, `make logs`.

**Когда:** опционально, при необходимости деплоя на чужую машину.

## Этап 12. CI

**Статус:** Backlog.

- [ ] `.github/workflows/test.yml`: setup-python + `pip install -r requirements.txt` + `pytest -q`.
- [ ] Линтер ruff в CI (ошибка → red).
- [ ] Бейдж в `README.md`.

**Когда:** после стабилизации тестов; перед публикацией репо публично.

## Этап 13. Sandboxed tools

**Статус:** Backlog.

Для tools, которые опасно запускать без изоляции (shell, произвольное чтение/запись ФС, sql-execute).

- [ ] `app/tools/sandboxed/` со своим контрактом `SandboxedTool`.
- [ ] Изоляция через `subprocess` + `chroot` / `firejail` / `podman` (на усмотрение).
- [ ] Whitelist команд / путей — конфигурируется через `.env`.

**Когда:** когда понадобится shell-tool или подобное (роадмап-кандидат, не приоритет).

## Этап 14. Точный токенайзер

**Статус:** Backlog.

Сейчас `estimate_tokens = chars / 4`. Для слабых моделей с маленьким окном это иногда неточно.

- [ ] `tiktoken` или HuggingFace tokenizer.
- [ ] Конфиг: `TOKENIZER_MODEL` (по умолчанию синхронизирован с LLM).
- [ ] Использовать в логах и в lint'ах перед `chat`-вызовом, чтобы предупреждать о переполнении контекста.

**Когда:** опционально, когда станет узким местом.

## Этап 15. Hot-reload скиллов и промптов

**Статус:** Backlog.

Сейчас правка `_skills/` и `_prompts/` требует рестарта процесса. Watcher на эти каталоги (через `watchdog`) автоматически перезагружает регистры.

- [ ] `SkillRegistry.watch(...)`.
- [ ] `PromptLoader.watch(...)`.

**Когда:** опционально, удобство разработки.

## Этап 16. Per-skill / per-task memory

**Статус:** Backlog.

Сейчас вся семантическая память — общий пул чанков. Расширения:

- [ ] Метка `skill_name` на чанках, фильтр по ней в `memory_search`.
- [ ] Краткое саммари каждой выполненной задачи (с tool calls + observations) для будущего Critic'а.

**Когда:** после Этапа 5.

## Ориентировочная последовательность

```
Этап 1 (Спринт 00) → Этап 2 (Спринт 01) → Этап 3 (UX) → Этап 5 (multi-agent)
                                        ↘ Этап 9 (скиллы)
                                        ↘ Этап 10 (throttling)  ↘ Этап 12 (CI)
                                        ↘ Этап 11 (Docker)
                                                                ↘ Этап 6 (web/MAX)
                                                                ↘ Этап 7 (webhook)
```

Этапы 4, 8 (доборные части), 13, 14, 15, 16 — backlog по запросу пользователя.

## Принципы планирования

- Один активный спринт за раз (см. `_board/process.md` §2 п.1).
- Новый спринт = новая ветка `feature/<NN>-<short-name>` (см. `_board/process.md` §2 п.2).
- Спринт оценивается в задачах, не в часах. Каждая задача проходит DoD из шаблона `_board/process.md` §4.2.
- При обнаружении легаси / нюанса — записываем в `_docs/current-state.md` §2; не правим попутно.
- Правила обновления самого `roadmap.md` — `_board/process.md` §8.2.
