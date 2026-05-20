# Спринт 07. Multi-agent (Planner + Critic)

- **Источник:** `_docs/roadmap.md` § «Этап 3. Multi-agent (Planner + Critic)»; запрос пользователя (20.05.2026).
- **Ветка:** `feature/07-multi-agent` (от `main`; см. `_board/process.md` §2 п.2).
- **Открыт:** 2026-05-20
- **Закрыт:** —

## 1. Цель спринта

Сейчас в `app/agents/` живёт единственный агент — `Executor` (`app/agents/executor.py`), и `core.handle_user_task` (`app/core/orchestrator.py`) дергает его напрямую. Для сложных задач этого не хватает: модель сама и планирует, и выполняет, и валидирует — на слабых локальных моделях это часто срывает цикл (см. §6.1–6.2 `_docs/current-state.md`).

Цель спринта — превратить проект из «one-agent loop» в реальный multi-agent: добавить `Planner` (декомпозиция задачи в линейный план шагов), `Critic` (валидация финального ответа `PASS|REVISE`) и расширить `core/orchestrator.py` так, чтобы вся новая логика была скрыта за тем же контрактом `core.handle_user_task(text, user_id, chat_id)` (см. `_docs/architecture.md` §3.10, §8.4) — адаптеры (Telegram, console) меняться не должны. По итогу спринта пользователь сможет переключать глубину рефлексии (`OFF | NORMAL | DEEP`) на лету через команду бота и видеть стабильно более качественные ответы на многошаговых задачах.

## 2. Скоуп и non-goals

### В скоупе

- Новый агент `app/agents/planner.py`: задача → линейный план шагов (JSON-протокол по аналогии с `app/agents/protocol.py`).
- Новый агент `app/agents/critic.py`: draft-ответ Executor → `PASS|REVISE` + feedback.
- Расширение `app/core/orchestrator.py`: `task → planner → executor (per-step) → [critic → revise]* → final`.
- Режимы рефлексии `OFF | NORMAL | DEEP` (выбор: пропуск Planner+Critic / один проход Critic / итеративный Critic с лимитом).
- Конфиг режима по умолчанию в `Settings` (`AGENT_REFLECTION_MODE`) + per-user override в `user_settings`.
- Команда бота `/mode` (Telegram + console) для переключения режима пользователем.
- Промпты `_prompts/planner.md`, `_prompts/critic.md` + загрузчик в существующем `PromptLoader`.
- Документация: новый `_docs/multi-agent.md`, обновление `_docs/architecture.md`, `_docs/agent-loop.md`, `_docs/commands.md`, `_docs/current-state.md`, `_docs/roadmap.md`.
- Unit-тесты на все новые компоненты + один сквозной интеграционный тест оркестратора с моком LLM.

### Вне скоупа (non-goals)

- Capability graph с переиспользованием результатов через `{{nodeId}}` (этап 3 roadmap, пункт «Capability graph») — выносим в отдельный кандидат на следующий спринт, чтобы спринт 07 остался обозримым.
- Per-skill / per-task memory (этап 14 roadmap, явно `Зависит от` Этапа 3).
- Stream-индикация шагов в Telegram (этап 1 roadmap).
- Внешние онлайн-LLM (этап 4 roadmap) — Planner и Critic используют тот же `OllamaClient`.
- Изменение формата `dialog_journal` / схемы `memory_chunks`.
- Любые правки tools и skills, не вызванные напрямую multi-agent контрактом.

## 3. Acceptance Criteria спринта

- [ ] Контракт `core.handle_user_task(text, user_id, chat_id)` не изменился; Telegram- и console-адаптеры не правились (кроме регистрации новой команды `/mode`).
- [ ] При `AGENT_REFLECTION_MODE=OFF` поведение бота идентично спринту 06 (один Executor, никаких лишних LLM-вызовов).
- [ ] При `AGENT_REFLECTION_MODE=NORMAL` для тестового сценария выполняется ровно один проход Critic; при `DEEP` — Critic итерируется не более `AGENT_REFLECTION_MAX_ITERATIONS` раз.
- [ ] `Planner` возвращает валидный линейный план (список шагов); при невалидном ответе оркестратор откатывается к single-step выполнению через Executor (graceful degradation), факт фиксируется в логах.
- [ ] `Critic` возвращает строго `{"verdict": "PASS"|"REVISE", "feedback": "..."}`; при невалидном ответе считается `PASS` (fail-open), факт фиксируется в логах.
- [ ] Команда `/mode` доступна в Telegram и console, меняет режим в `user_settings`, документирована в `_docs/commands.md`.
- [ ] `pytest -q` и `flake8 app tests` зелёные; добавлены тесты Planner, Critic, orchestrator-интеграция (мок LLM).
- [ ] `_docs/multi-agent.md` создан; `_docs/architecture.md` §3.10 / §3.11, `_docs/agent-loop.md`, `_docs/current-state.md` §1, `_docs/roadmap.md` (удалить Этап 3) актуализированы.
- [ ] Все задачи спринта — `Done`, сводная таблица актуальна.

## 4. Этап 1. Конфиг и протоколы

Перед написанием агентов закрепляем контракт: режимы рефлексии в `Settings`, JSON-протоколы Planner/Critic в `app/agents/protocol.py` (или соседнем модуле), чтобы остальные задачи опирались на стабильные структуры данных.

### Задача 1.1. Режимы рефлексии в `Settings` и `user_settings`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/stack.md` §9 (конфиг), `_docs/architecture.md` §3.2–3.3.
- **Затрагиваемые файлы:** `app/config.py`, `app/services/user_settings.py` (или эквивалент), `.env.example`.

#### Описание

1. В `app/config.py` добавить поля `agent_reflection_mode: Literal["OFF","NORMAL","DEEP"] = "OFF"` и `agent_reflection_max_iterations: int = 2` (DEEP — верхняя граница итераций Critic).
2. В `.env.example` добавить `AGENT_REFLECTION_MODE=OFF` и `AGENT_REFLECTION_MAX_ITERATIONS=2` с комментарием.
3. В per-user store (`user_settings`) добавить override `reflection_mode` (None → fallback на `Settings`).
4. Не использовать новые поля нигде в логике в этой задаче — только зарегистрировать.

#### Definition of Done

- [x] `Settings()` парсит новые переменные из `.env`; есть значения по умолчанию.
- [x] `user_settings` умеет хранить и читать `reflection_mode` per-user.
- [x] **Документация обновлена** — добавить упоминание в `_docs/stack.md` §9.
- [x] **Тесты добавлены / обновлены** — короткий тест на парсинг `.env` и per-user override.
- [x] `git status` чист.

### Задача 1.2. Протоколы Planner и Critic

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/agent-loop.md` §2 (формат ответа Executor — как образец).
- **Затрагиваемые файлы:** `app/agents/protocol.py` (расширение) или новый `app/agents/multi_agent_protocol.py`.

#### Описание

1. Добавить dataclass'ы `PlanStep(id: int, description: str)` и `Plan(steps: list[PlanStep])`.
2. Добавить функцию `parse_planner_response(text: str) -> Plan` с тем же подходом толерантности к markdown-fence, что и `parse_agent_response` (см. `_docs/current-state.md` §6.1).
3. Добавить dataclass `CriticVerdict(verdict: Literal["PASS","REVISE"], feedback: str)` и `parse_critic_response(text: str) -> CriticVerdict`.
4. Невалидный JSON → `LLMBadResponse` (уже существует).

#### Definition of Done

- [x] Парсеры покрыты юнит-тестами (валидный JSON, markdown-fence, мусор → `LLMBadResponse`, неизвестный `verdict` → `LLMBadResponse`).
- [x] `pytest tests/agents -q` зелёный.
- [x] **Документация обновлена** — `n/a` (новый `_docs/multi-agent.md` появится в задаче 5.1, контракт зафиксируется там).
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 5. Этап 2. Planner

Декомпозиция задачи в линейный план шагов. План передаётся Executor'у как контекст и/или последовательность подцелей.

### Задача 2.1. Промпт `_prompts/planner.md`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.2.
- **Связанные документы:** `_docs/prompts.md`, `_prompts/agent_system.md` (как образец стиля).
- **Затрагиваемые файлы:** `_prompts/planner.md`, `app/services/prompts.py` (или эквивалент `PromptLoader`).

#### Описание

1. Создать `_prompts/planner.md` с инструкцией: на вход — задача пользователя, на выход — **строгий JSON** `{"steps": [{"id": 1, "description": "..."}, ...]}` без markdown-fence (зафиксировать урок 6.1).
2. Ограничить: 1–6 шагов, описание шага ≤ 200 символов, без вложенных планов.
3. В `PromptLoader` добавить метод `render_planner(task: str) -> str`.

#### Definition of Done

- [x] `_prompts/planner.md` существует, синтаксис консистентен с `agent_system.md`.
- [x] `PromptLoader.render_planner` покрыт юнит-тестом.
- [x] **Документация обновлена** — `_docs/prompts.md` (упомянут новый промпт и плейсхолдер `{{TASK}}`).
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

### Задача 2.2. `PlannerAgent`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.1, Задача 1.2.
- **Связанные документы:** `_docs/multi-agent.md` (создаётся в 5.1), `_docs/architecture.md` §3.11.
- **Затрагиваемые файлы:** `app/agents/planner.py` (новый), `tests/agents/test_planner.py` (новый).

#### Описание

1. Реализовать класс `PlannerAgent(llm, prompts, settings)` с методом `async def plan(task: str, *, user_id: int, model: str | None) -> Plan`.
2. Внутри: рендерим системный промпт, вызываем `llm.chat`, парсим `parse_planner_response`. На `LLMBadResponse` — возвращаем `Plan(steps=[PlanStep(1, task)])` (fallback, логируется как `planner.fallback`).
3. Структурные логи `external.call` / `external.ok` / `external.fail` по аналогии с `app/services/llm.py` (см. `_docs/observability.md` §1–§4).

#### Definition of Done

- [x] `PlannerAgent.plan` покрыт юнит-тестами: happy-path (валидный JSON), markdown-fence, мусорный ответ → fallback, пустой `steps` → fallback.
- [x] Логи содержат `service=planner`, `user_id` (`trace_id` пока не связан на уровне агента — пробросится в задаче 4.1 через logging-context).
- [x] **Документация обновлена** — `n/a` (будет в задаче 5.1).
- [x] **Тесты добавлены / обновлены** — да (`tests/agents/test_planner.py`, 11 тестов).
- [x] `git status` чист.

## 6. Этап 3. Critic

Валидация финального ответа Executor: PASS → отдаём пользователю, REVISE → запускаем Executor повторно с фидбеком (NORMAL — один проход, DEEP — до `agent_reflection_max_iterations`).

### Задача 3.1. Промпт `_prompts/critic.md`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.2.
- **Связанные документы:** `_docs/prompts.md`.
- **Затрагиваемые файлы:** `_prompts/critic.md`, `app/services/prompts.py`.

#### Описание

1. Создать `_prompts/critic.md`: на вход — исходная задача + план + draft-ответ; на выход — JSON `{"verdict": "PASS"|"REVISE", "feedback": "..."}`.
2. Критерии: соответствие задаче, фактическая точность (где проверяемо), отсутствие галлюцинаций, формат. `feedback` обязателен при `REVISE`, опционален при `PASS`.
3. В `PromptLoader` добавить `render_critic(task, plan, draft) -> str`.

#### Definition of Done

- [x] `_prompts/critic.md` существует.
- [x] `PromptLoader.render_critic` покрыт юнит-тестом (6 тестов в `tests/services/test_prompts.py`).
- [x] **Документация обновлена** — `_docs/prompts.md`.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

### Задача 3.2. `CriticAgent`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 3.1, Задача 1.2.
- **Связанные документы:** `_docs/multi-agent.md` (создаётся в 5.1).
- **Затрагиваемые файлы:** `app/agents/critic.py` (новый), `tests/agents/test_critic.py` (новый).

#### Описание

1. Класс `CriticAgent(llm, prompts, settings)` с `async def review(task, plan, draft, *, user_id, model) -> CriticVerdict`.
2. На `LLMBadResponse` или неизвестный verdict — fail-open: возвращаем `CriticVerdict("PASS", "")`, лог `critic.fallback`.
3. Структурные логи `service=critic`.

#### Definition of Done

- [x] Юнит-тесты: PASS, REVISE с feedback, невалидный JSON → fallback, неизвестный verdict → fallback (10 тестов в `tests/agents/test_critic.py`).
- [x] Логи с `user_id` (`trace_id` пробросится в задаче 4.1 через logging-context, симметрично Planner'у).
- [x] **Документация обновлена** — в задаче 5.1.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 7. Этап 4. Оркестрация и команда `/mode`

Связываем всё в `core/orchestrator.py` и даём пользователю ручку управления.

### Задача 4.1. Расширить `core.handle_user_task`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** L
- **Зависит от:** Задача 2.2, Задача 3.2, Задача 1.1.
- **Связанные документы:** `_docs/architecture.md` §3.10, `_docs/agent-loop.md`.
- **Затрагиваемые файлы:** `app/core/orchestrator.py`, `app/main.py` (DI), `app/console_main.py` (DI).

#### Описание

1. Определить эффективный режим: `user_settings.reflection_mode or settings.agent_reflection_mode`.
2. При `OFF` — текущая логика без изменений (Executor напрямую).
3. При `NORMAL`/`DEEP`:
   1. `planner.plan(task)` → `Plan` (логировать `plan.steps_count`).
   2. План прикладывается к `goal` Executor'a как контекст (`План: 1) ... 2) ...`). Executor вызывается **один раз** (per-step выполнение шагов оставляем за Executor'ом — он уже умеет действовать в цикле).
   3. `critic.review(task, plan, draft)`.
   4. `PASS` → возвращаем draft.
   5. `REVISE` → повторный вызов Executor с goal вида `Исходная задача: {task}\nЧерновик: {draft}\nЗамечания: {feedback}\nИсправь ответ.` Лимит итераций — `agent_reflection_max_iterations` при `DEEP`, ровно 1 при `NORMAL`.
4. Graceful degradation: любые исключения Planner/Critic не должны валить запрос — фиксируется в логах, возвращаем последний доступный draft.
5. Контракт сигнатуры `handle_user_task` не меняется.

#### Definition of Done

- [x] Сигнатура `handle_user_task` сохранена; новые зависимости (`planner`, `critic`, `user_settings`) добавлены как kwargs с `None` по умолчанию; DI прописан в `main.py` и `console_main.py` + прокинут через `messages.py` без изменения публичного контракта хендлеров.
- [x] Юнит-тесты `tests/core/test_orchestrator.py` покрывают ветки OFF / NORMAL-PASS / NORMAL-REVISE / DEEP-лимит / DEEP-PASS-на-2 / per-user override / planner-fallback / critic-fail-open (9 новых тестов).
- [x] Логирование шагов: `orchestrator.mode`, `orchestrator.planner_ok|planner_fallback`, `orchestrator.iteration` (с verdict), `orchestrator.critic_error|revise_error`.
- [x] **Документация обновлена** — `_docs/architecture.md` §3.11 переписан, `_docs/agent-loop.md` перенаправлен на `multi-agent.md` (появится в задаче 5.1).
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

### Задача 4.2. Команда `/mode`

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 1.1, Задача 4.1.
- **Связанные документы:** `_docs/commands.md`, `_docs/console-adapter.md`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py`, `app/adapters/console/adapter.py`, `app/commands/registry.py` (если применимо).

#### Описание

1. `/mode` без аргумента — показать текущий режим и доступные значения.
2. `/mode off|normal|deep` — установить per-user override через `user_settings`.
3. Реализовать одинаково в Telegram и console (использовать общий `commands/registry.py`, если он уже централизует команды; иначе — продублировать минимально).
4. Ответ форматировать с HTML-экранированием (см. `_docs/current-state.md` §3, нюанс `parse_mode=ParseMode.HTML`).

#### Definition of Done

- [ ] Команда работает в Telegram и в console; покрыта юнит-тестом per адаптер.
- [ ] **Документация обновлена** — `_docs/commands.md`, `_docs/console-adapter.md`.
- [ ] **Тесты добавлены / обновлены** — да.
- [ ] `git status` чист.

### Задача 4.3. Сквозной интеграционный тест оркестратора

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 4.1, Задача 4.2.
- **Связанные документы:** `_docs/testing.md`.
- **Затрагиваемые файлы:** `tests/test_multi_agent_e2e.py` (новый).

#### Описание

Сценарий на мок-LLM: пользователь шлёт задачу через `core.handle_user_task` с `reflection_mode=DEEP`; мок возвращает по очереди план → draft → REVISE feedback → улучшенный draft → PASS. Проверить итоговый текст, количество вызовов LLM, факт записи в `dialog_journal` (если применимо).

#### Definition of Done

- [ ] Тест проходит, изолирован от сети, не дёргает реальную Ollama.
- [ ] **Документация обновлена** — `n/a`.
- [ ] **Тесты добавлены / обновлены** — да.
- [ ] `git status` чист.

## 8. Этап 5. Документация и синхронизация roadmap

Закрываем спринт «бумагой»: фиксируем фактическое состояние, переносим Этап 3 из roadmap в историю, проверяем ссылки.

### Задача 5.1. Новый `_docs/multi-agent.md`

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 4.1, Задача 4.2.
- **Связанные документы:** `_docs/architecture.md`, `_docs/agent-loop.md`, `_docs/README.md` (навигация).
- **Затрагиваемые файлы:** `_docs/multi-agent.md` (новый), `_docs/README.md`, `_docs/project-structure.md`.

#### Описание

Описать: роли Planner / Executor / Critic, контракт JSON-протоколов, режимы `OFF|NORMAL|DEEP`, диаграмма потока, поведение fallback'ов, конфиг (`AGENT_REFLECTION_MODE`, `AGENT_REFLECTION_MAX_ITERATIONS`), команда `/mode`. Только относительные пути (см. `_board/process.md` §8 п.7).

#### Definition of Done

- [ ] Файл создан, добавлен в навигацию `_docs/README.md` и в `_docs/project-structure.md`.
- [ ] Ссылки прогнаны `grep`-ом, обновлены все живые упоминания (см. `_board/process.md` §8 п.6).
- [ ] **Документация обновлена** — да, это и есть задача.
- [ ] **Тесты добавлены / обновлены** — `n/a`.
- [ ] `git status` чист.

### Задача 5.2. Обновить `current-state.md` и `roadmap.md`

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 5.1.
- **Связанные документы:** `_docs/current-state.md` §1, `_docs/roadmap.md`.
- **Затрагиваемые файлы:** `_docs/current-state.md`, `_docs/roadmap.md`.

#### Описание

1. В `_docs/current-state.md` §1 добавить новую подсекцию «1.8 Multi-agent» с перечнем компонентов (Planner, Critic, режимы) и ссылками на файлы.
2. В §3 (архитектурные нюансы) добавить пункт о fail-open поведении Critic и fallback Planner.
3. В `_docs/roadmap.md` удалить «Этап 3. Multi-agent (Planner + Critic)»; если capability graph выводится в отдельный этап — оставить его в roadmap как Backlog «Capability graph (переиспользование `{{nodeId}}`)».
4. Перенумеровать оставшиеся этапы roadmap **не нужно** — нумерация в `roadmap.md` логическая, не порядковая (см. сам файл).

#### Definition of Done

- [ ] `_docs/current-state.md` §1.8 и §3 актуальны.
- [ ] `_docs/roadmap.md` не содержит «Этап 3» в прежнем виде; capability graph либо отдельным backlog-пунктом, либо запись «закрыт спринтом 07».
- [ ] **Документация обновлена** — да.
- [ ] **Тесты добавлены / обновлены** — `n/a`.
- [ ] `git status` чист.

## 9. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Локальная модель (`qwen3.5:4b`) даёт нестабильный JSON для Planner/Critic — слишком много fallback'ов. | Чёткие промпты с примерами + толерантный парсер (markdown-fence как в задаче 6.1 спринта 02); fail-open поведение Critic; задача 4.3 фиксирует поведение на мок-LLM, реальный smoke — после merge. |
| 2 | Multiplier на количество LLM-вызовов (×2–×4) ломает p95 latency. | Режим по умолчанию `OFF`; `NORMAL` — ровно 1 проход Critic; `DEEP` — лимит `AGENT_REFLECTION_MAX_ITERATIONS` (default 2). Структурные логи `external.call` (см. `_docs/observability.md`) позволят увидеть деградацию. |
| 3 | Расползание контракта `handle_user_task` сломает Telegram/console-адаптеры. | AC спринта явно фиксирует неизменность сигнатуры; новые зависимости — kwargs со значением `None`; DI правится только в `main.py` и `console_main.py`. |
| 4 | Capability graph (`{{nodeId}}`) при попытке «дотащить в этот же спринт» раздует scope. | Явный non-goal §2; вынесено в roadmap как отдельный кандидат. |
| 5 | `/mode` нарушит существующий тест на список команд. | Тесты `tests/adapters/telegram/test_commands.py` и `tests/adapters/console/*` правятся в задаче 4.2 синхронно с реализацией. |

## 10. Сводная таблица задач спринта

| #   | Задача                                                | Приоритет | Объём | Статус | Зависит от        |
|-----|-------------------------------------------------------|:---------:|:-----:|:------:|:-----------------:|
| 1.1 | Режимы рефлексии в `Settings` и `user_settings`       | high      | S     | Done   | —                 |
| 1.2 | Протоколы Planner и Critic                            | high      | S     | Done   | —                 |
| 2.1 | Промпт `_prompts/planner.md`                          | high      | S     | Done   | 1.2               |
| 2.2 | `PlannerAgent`                                        | high      | M     | Done   | 2.1, 1.2          |
| 3.1 | Промпт `_prompts/critic.md`                           | high      | S     | Done   | 1.2               |
| 3.2 | `CriticAgent`                                         | high      | M     | Done   | 3.1, 1.2          |
| 4.1 | Расширить `core.handle_user_task`                     | high      | L     | Done   | 2.2, 3.2, 1.1     |
| 4.2 | Команда `/mode`                                       | medium    | S     | ToDo   | 1.1, 4.1          |
| 4.3 | Сквозной интеграционный тест оркестратора             | medium    | S     | ToDo   | 4.1, 4.2          |
| 5.1 | Новый `_docs/multi-agent.md`                          | high      | M     | ToDo   | 4.1, 4.2          |
| 5.2 | Обновить `current-state.md` и `roadmap.md`            | medium    | S     | ToDo   | 5.1               |

> Обновляется при каждом переходе статуса и при добавлении/удалении задач.

## 11. История изменений спринта

- **2026-05-20** — спринт открыт, ветка `feature/07-multi-agent` создана от `main`.
- **2026-05-20** — задача 07.1.1 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.1.1: `agent_reflection_mode` / `agent_reflection_max_iterations` в `Settings`, per-user `reflection_mode` в `UserSettingsRegistry`, тесты + `_docs/stack.md` §9.
- **2026-05-20** — задача 07.1.2 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.1.2: `PlanStep`/`Plan`/`CriticVerdict` + парсеры `parse_planner_response`/`parse_critic_response` в `app/agents/protocol.py`, 21 unit-тест. Этап 1 завершён.
- **2026-05-20** — задача 07.2.1 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.2.1: `_prompts/planner.md` + `PromptLoader.render_planner` + тесты + `_docs/prompts.md`.
- **2026-05-20** — задача 07.2.2 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.2.2: `PlannerAgent` (`app/agents/planner.py`) + 11 unit-тестов, fallback на single-step при любой ошибке LLM/парсера. Этап 2 завершён.
- **2026-05-20** — задача 07.3.1 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.3.1: `_prompts/critic.md` + `PromptLoader.render_critic` (плейсхолдеры `{{TASK}}`/`{{PLAN}}`/`{{DRAFT}}`) + 6 unit-тестов + `_docs/prompts.md`.
- **2026-05-20** — задача 07.3.2 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.3.2: `CriticAgent` (`app/agents/critic.py`) + 10 unit-тестов, fail-open поведение (PASS при любой ошибке LLM/парсера). Этап 3 завершён.
- **2026-05-20** — задача 07.4.1 взята в работу (`ToDo` → `Progress`).
- **2026-05-20** — закрыта задача 07.4.1: оркестратор расширен режимами OFF/NORMAL/DEEP (Planner+Executor+Critic), DI в `main.py`/`console_main.py`, 9 новых юнит-тестов, обновлён `architecture.md` §3.11.
