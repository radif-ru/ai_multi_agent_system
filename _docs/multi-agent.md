# Multi-agent (Planner + Executor + Critic)

Документ описывает мульти-агентную надстройку над Executor: роли агентов, JSON-протоколы, режимы рефлексии `OFF | NORMAL | DEEP`, поведение fallback'ов, конфиг и команду `/mode`. Реализация — спринт 07 (`_board/sprints/07-multi-agent.md`).

Связанные документы:

- [`agent-loop.md`](./agent-loop.md) — внутренний цикл Executor (`thought → action → observation`); в режиме `OFF` поведение совпадает с описанным там.
- [`architecture.md`](./architecture.md) §3.11 — место `handle_user_task` в архитектуре.
- [`prompts.md`](./prompts.md) — формат промптов Planner / Critic.
- [`commands.md`](./commands.md) — команда `/mode`.
- [`stack.md`](./stack.md) §9 — переменные окружения `AGENT_REFLECTION_MODE`, `AGENT_REFLECTION_MAX_ITERATIONS`.
- [`observability.md`](./observability.md) §1–§4 — структурные логи (`service`, `external.call/ok/fail`).

## 1. Роли агентов

| Агент | Файл | Вход | Выход | Назначение |
|-------|------|------|-------|------------|
| **Planner** | `app/agents/planner.py` | задача пользователя | `Plan` (1–6 шагов) | декомпозиция задачи в линейный план |
| **Executor** | `app/agents/executor.py` | `goal` (с подмешанным планом) + история | финальный текст (draft) | агентный цикл `thought → action → observation` (см. `agent-loop.md`) |
| **Critic** | `app/agents/critic.py` | задача + план + draft | `CriticVerdict` (`PASS|REVISE` + feedback) | валидация draft-ответа |

`Executor` остаётся единственным агентом, имеющим доступ к tools/skills. Planner и Critic — это **одиночные LLM-вызовы** без tools.

## 2. Контракт JSON-протоколов

Парсеры — `app/agents/protocol.py` (`parse_planner_response`, `parse_critic_response`). Толерантны к markdown-fence (` ```json … ``` `), как `parse_agent_response` (см. урок 6.1 в `current-state.md` §6.1).

### 2.1 Planner

Запрос: `app/prompts/planner.md` (плейсхолдер `{{TASK}}`).

Ответ — строго JSON, без markdown-fence:

```json
{
  "steps": [
    {"id": 1, "description": "..."},
    {"id": 2, "description": "..."}
  ]
}
```

Жёсткие лимиты (синхронизированы с константами `PLAN_*` в `protocol.py` и инструкцией в промпте):

- 1–6 шагов;
- `id` — `int`;
- `description` — непустая строка ≤ 200 символов;
- без вложенных планов.

Любое отклонение → `LLMBadResponse` → fallback (см. §4).

### 2.2 Critic

Запрос: `app/prompts/critic.md` (плейсхолдеры `{{TASK}}`, `{{PLAN}}`, `{{DRAFT}}`).

Ответ — строго JSON:

```json
{"verdict": "PASS",   "feedback": ""}
{"verdict": "REVISE", "feedback": "Что и как поправить."}
```

- `verdict` — только `"PASS"` или `"REVISE"` (case-insensitive на парсинге, нормализуется в верхний регистр);
- `feedback` — строка; **обязательна и непуста при `REVISE`**, опциональна при `PASS`.

Любое отклонение → `LLMBadResponse` → fail-open (см. §4).

## 3. Режимы рефлексии

Конфигурируется через `Settings.agent_reflection_mode` (`OFF | NORMAL | DEEP`, default `OFF`) и `Settings.agent_reflection_max_iterations` (default `2`, верхняя граница итераций Critic в `DEEP`). Per-user override — `UserSettingsRegistry.get_reflection_mode(user_id)`.

| Режим | LLM-вызовы (минимум) | Поведение |
|-------|---------------------:|-----------|
| `OFF` | 1 (Executor) | Executor напрямую, как в спринте 06. Planner/Critic не вызываются даже если переданы в DI. |
| `NORMAL` | 3 (Planner + Executor + Critic) | Один проход Critic. `PASS` → возврат draft; `REVISE` → один re-run Executor с фидбеком, возврат итогового draft без повторной проверки. |
| `DEEP` | 3 + 2·(N−1) | Critic итерируется до `agent_reflection_max_iterations`. На каждой итерации `PASS` → возврат немедленно; `REVISE` → re-run Executor; после исчерпания лимита возвращается последний draft. |

Эффективный режим выбирает `_resolve_mode` в `app/core/orchestrator.py`: per-user override приоритетнее `Settings`. Если `planner` или `critic` не переданы в `handle_user_task` — режим **даунгрейдится в `OFF`** независимо от настройки (защита от рассогласования DI).

## 4. Поведение fallback'ов (graceful degradation)

Multi-agent надстройка обязана **никогда не валить запрос пользователя** из-за ошибок Planner/Critic. Реализация в `app/core/orchestrator.py`:

| Точка отказа | Поведение | Лог |
|--------------|-----------|-----|
| `Planner.plan` бросает (LLM down, `LLMBadResponse`, …) | даунгрейд: Executor.run на исходный `text` | `orchestrator.planner_fallback` (WARNING) |
| `Planner` вернул валидный, но непригодный JSON | внутри `PlannerAgent` ловится → `Plan(steps=[PlanStep(1, task)])` | `planner.fallback` (агентный лог) |
| `Critic.review` бросает | возврат текущего `draft` без дальнейших итераций | `orchestrator.critic_error` (WARNING) |
| `Critic` вернул мусор / неизвестный verdict | внутри `CriticAgent` → `CriticVerdict("PASS", "")` (fail-open) | `critic.fallback` (агентный лог) |
| Re-run Executor (`REVISE`) бросает | возврат предыдущего `draft` | `orchestrator.revise_error` (WARNING) |

Контракт `core.handle_user_task(text, user_id, chat_id)` стабилен для адаптеров — в любом сценарии возвращается строка для пользователя.

## 5. Поток

```
adapter (Telegram / console)
        │  text, user_id, chat_id
        ▼
core.handle_user_task
        │
        ├─ resolve_mode(user_settings, settings)
        │
        ├── OFF ──► Executor.run(goal=text) ──► final
        │
        └── NORMAL / DEEP
                │
                ▼
            Planner.plan(text) ──► Plan
                │  (план подмешивается в goal как
                │   "Исходная задача …\n\nПлан выполнения:\n1) …\n2) …")
                ▼
            Executor.run(goal=augmented) ──► draft
                │
                ▼
            ┌── Critic.review(text, plan, draft) ◄──┐
            │                                       │
            │   PASS ──► return draft               │
            │                                       │
            │   REVISE (и iter < limit) ────────────┤
            │     Executor.run(goal=revise_goal)    │
            │       ──► draft' ─────────────────────┘
            │
            └── iter == limit ──► return last draft
```

`limit` = `1` для `NORMAL`, `Settings.agent_reflection_max_iterations` для `DEEP`.

`revise_goal` формируется в `_augment_goal_with_plan` соседним хелпером и имеет вид:

```
Исходная задача: {text}
Черновик: {draft}
Замечания: {feedback}
Исправь ответ.
```

## 6. Конфигурация

`.env` (см. `stack.md` §9):

```env
AGENT_REFLECTION_MODE=OFF              # OFF | NORMAL | DEEP
AGENT_REFLECTION_MAX_ITERATIONS=2      # верхняя граница итераций Critic в DEEP
```

Per-user override хранится в `UserSettingsRegistry` (`app/services/model_registry.py`) и выставляется командой `/mode`.

## 7. Команда `/mode`

Реализация — `app/commands/registry.py` (общий контракт для Telegram и console). См. `commands.md` §`/mode` и `console-adapter.md`.

- `/mode` без аргументов — показать текущий эффективный режим и список доступных значений.
- `/mode off|normal|deep` — установить per-user override (case-insensitive).
- Сброс per-user override — выставить значение, совпадающее с `Settings.agent_reflection_mode`, либо очистить через future-команду (вне scope спринта 07).

## 8. Логирование и наблюдаемость

В дополнение к `external.call/ok/fail` в `OllamaClient` (см. `observability.md` §1–§4) оркестратор пишет:

| Лог | Поля | Когда |
|-----|------|-------|
| `orchestrator.mode` | `mode`, `user_id` | каждый вход в `handle_user_task` (после `_resolve_mode`) |
| `orchestrator.planner_ok` | `user_id`, `steps_count` | успешный план |
| `orchestrator.planner_fallback` | `user_id`, `err` | исключение Planner |
| `orchestrator.iteration` | `user_id`, `iteration`, `verdict` | каждая итерация Critic |
| `orchestrator.critic_error` | `user_id`, `iteration`, `err` | исключение Critic |
| `orchestrator.revise_error` | `user_id`, `iteration`, `err` | исключение re-run Executor |

Внутри агентов — `service=planner` / `service=critic`, `external.call|ok|fail` от `OllamaClient`.

## 9. Не входит в multi-agent (на 2026-05-20)

- **Capability graph** с переиспользованием результатов узлов через `{{nodeId}}` — backlog в `roadmap.md`.
- **Per-skill / per-task memory** — отдельный этап в `roadmap.md` (зависит от multi-agent).
- **Stream-индикация шагов** в Telegram — отдельный этап в `roadmap.md`.
- **Параллельное выполнение шагов плана** — план линейный, шаги склеиваются в один `goal` Executor'у; Executor сам решает, как их выполнять в своём цикле.
