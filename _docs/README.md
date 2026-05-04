# Документация проекта

AI-агент с локальной LLM (Ollama), работающий в цикле `thought → action → observation`. Сейчас — Telegram-интерфейс через [aiogram 3](https://docs.aiogram.dev/), в перспективе — мульти-агентная система (Planner / Executor / Critic) с web-адаптером и адаптером в мессенджер MAX. Документы здесь описывают цели, архитектуру, текущее состояние кода, правила разработки и процесса.

## Источник истины

- Корневой `README.md` — пользовательское описание проекта (что это, как установить, какие команды).
- `CLAUDE.md` — поведенческие гайдлайны LLM-агента (общие, не проектные).
- Документы в этой папке — формализация фактического состояния кода в `app/` на момент написания. **При расхождении с кодом приоритет у кода**, документ должен быть подправлен следующим коммитом.
- `_skills/` и `_prompts/` — содержательные артефакты, которые подмешиваются в системный промпт агента в рантайме (см. `skills.md`, `prompts.md`).

## Навигация

### Что это за проект и зачем

- [`mvp.md`](./mvp.md) — scope первого MVP (спринт 01) и критерии приёмки.
- [`requirements.md`](./requirements.md) — формализованные функциональные / нефункциональные требования (FR / NFR / CON / ASM) и трассировка.
- [`current-state.md`](./current-state.md) — что реально работает, что криво, известные баги, легаси-нюансы. **Читать обязательно перед любыми правками.**
- [`roadmap.md`](./roadmap.md) — этапы развития: multi-agent (Planner / Critic), web-адаптер, MAX-адаптер, отложенные улучшения.
- [`legacy.md`](./legacy.md) — сводный указатель на технический долг (ссылки на `current-state.md` §2 и этапы `roadmap.md`, без дублирования).

### Как устроено

- [`architecture.md`](./architecture.md) — компоненты, поток данных, агентный цикл, обработка ошибок, точки расширения под мульти-агент.
- [`agent-loop.md`](./agent-loop.md) — формат JSON-ответа модели (`{thought, action, args}` / `{final_answer}`), правила цикла, лимиты, защита от зацикливания.
- [`memory.md`](./memory.md) — краткосрочная in-memory история и долгосрочная семантическая память на `sqlite-vec` (RAG), сценарий `/new`.
- [`tools.md`](./tools.md) — реестр tools, контракт нового инструмента, текущий набор (calculator, read_file, http_request, web_search, memory_search, load_skill).
- [`skills.md`](./skills.md) — формат `_skills/<name>/SKILL.md`, как агент решает их подгрузить, как описание инжектится в промпт.
- [`prompts.md`](./prompts.md) — формат `_prompts/`, как файлы прокидываются через `.env`-пути.
- [`stack.md`](./stack.md) — стек, версии, зависимости, переменные окружения, локальные требования.
- [`project-structure.md`](./project-structure.md) — структура репозитория, назначение модулей, правила размещения файлов.

### Как этим пользоваться и как разрабатывать

- [`console-adapter.md`](./console-adapter.md) — спецификация консольного режима (REPL-цикл, команды, запуск через `python -m app.console`).
- [`commands.md`](./commands.md) — спецификация команд бота и поведения произвольного текста.
- [`testing.md`](./testing.md) — стратегия и категории тестов, моки, покрытие, обязательность тестов перед коммитом.
- [`instructions.md`](./instructions.md) — правила разработки: стиль, git, async, ошибки, секреты, тесты, документация.

### Справочное

- [`vision-models.md`](./vision-models.md) — рекомендации по vision-моделям для Ollama (gemma3:4b, llava-phi3 и др.).
- [`links.md`](./links.md) — каталог внешних ссылок: aiogram, Ollama, sqlite-vec, ddgs, pydantic-settings, pytest и др.

## Порядок чтения

1. **Новый агент / разработчик на проекте**: `CLAUDE.md` → `_docs/README.md` (этот файл) → `architecture.md` → `agent-loop.md` → `project-structure.md` → `current-state.md` → `roadmap.md`.
2. **Перед написанием кода**: `instructions.md` + `stack.md` + затронутый раздел (`commands.md` / `architecture.md` / `tools.md` / `memory.md`).
3. **При багфиксе или изменении конфигурации**: `current-state.md` (есть ли уже запись) → `stack.md` §9 (env-переменные) → код в `app/`.
4. **При планировании спринта**: `roadmap.md` → задача попадает в `_board/sprints/<NN>-<short-name>.md`.

## Связь с `_board/`

- `_docs/` — спецификация и состояние проекта (что и как).
- `_board/` — процесс и текущие задачи (что делаем сейчас).
- Точка входа для нового LLM-агента: `CLAUDE.md` → `_docs/README.md` → `_board/README.md` → `_board/plan.md` → `_board/sprints/<active>.md` → `_board/process.md`.

## Связь с `_skills/` и `_prompts/`

- `_docs/skills.md` — описывает **формат** скилла и как он инжектится в промпт.
- `_skills/<name>/SKILL.md` — содержит **сам скилл** (markdown с инструкциями для агента).
- `_docs/prompts.md` — описывает **формат** системных промптов и их роль в цикле.
- `_prompts/agent_system.md`, `_prompts/summarizer.md` — содержат **сами промпты**.

## Язык документации

Документы в этой папке — на русском. Технические идентификаторы (имена модулей, функций, переменных, env, путей) — латиницей, как в коде. Английские термины индустрии (LLM, RAG, polling, middleware, async, tool, skill, embedding) не переводим.
