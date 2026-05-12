# План — индекс спринтов

`plan.md` — **индекс спринтов** (только таблицы: активные, закрытые, запланированные). Правила работы со спринтами и задачами, легенды, шаблоны и пошаговый процесс — см. [`_board/process.md`](./process.md).

В таблицу «Запланированные» попадают **только реально созданные** файлы `_board/sprints/<NN>-<short-name>.md` со статусом `ToDo` (ветка ещё не создана). Идеи без файла спринта живут в [`_docs/roadmap.md`](../_docs/roadmap.md) (см. `process.md` §6.1 и §8.2).

## Индекс спринтов

### Активные

| ID | Название | Файл | Ветка | Статус | Открыт | Закрыт |
|:--:|----------|------|-------|:------:|:------:|:------:|
| 06 | Надёжность диалога и observability | [`sprints/06-reliability-and-observability.md`](./sprints/06-reliability-and-observability.md) | `feature/06-reliability-and-observability` | Active | 2026-05-10 | — |

### Закрытые

| ID | Название | Файл | Ветка | Статус | Открыт | Закрыт |
|:--:|----------|------|-------|:------:|:------:|:------:|
| 00 | Bootstrap | [`sprints/00-bootstrap.md`](./sprints/00-bootstrap.md) | `main` (инфраструктурный) | Closed | 2026-04-28 | 2026-04-28 |
| 01 | MVP Agent | [`sprints/01-mvp-agent.md`](./sprints/01-mvp-agent.md) | `feature/mvp-agent` | Closed | 2026-04-28 | 2026-04-28 |
| 02 | Память и файловые входы | [`sprints/02-memory-and-files.md`](./sprints/02-memory-and-files.md) | `feature/02-memory-and-files` | Closed | 2026-04-29 | 2026-04-29 |
| 03 | Исправление багов и консольный режим | [`sprints/03-bugs-and-console.md`](./sprints/03-bugs-and-console.md) | `feature/03-bugs-and-console` | Closed | 2026-04-30 | 2026-05-04 |
| 04 | Событийная модель и модуль Users | [`sprints/04-events-and-users.md`](./sprints/04-events-and-users.md) | `feature/04-events-and-users` | Closed | 2026-05-05 | 2026-05-06 |
| 05 | Усиление безопасности и OCR-рефакторинг | [`sprints/05-security-ocr.md`](./sprints/05-security-ocr.md) | `feature/05-security-ocr` | Closed | 2026-05-06 | 2026-05-06 |

### Запланированные

| ID | Название | Файл | Источник |
|:--:|----------|------|----------|
| — | — | — | — |

> Пусто: ни один файл будущего спринта пока не создан. Кандидаты на спринты — в [`_docs/roadmap.md`](../_docs/roadmap.md).

## Сводная таблица состояния

| Спринт | Статус | Задач (ToDo / Progress / Done) | Файл |
|--------|:------:|:------------------------------:|------|
| 00. Bootstrap | Closed | 0 / 0 / 5 | `sprints/00-bootstrap.md` |
| 01. MVP Agent | Closed | 0 / 0 / 28 | `sprints/01-mvp-agent.md` |
| 02. Память и файловые входы | Closed | 0 / 0 / 18 | `sprints/02-memory-and-files.md` |
| 03. Исправление багов и консольный режим | Closed | 0 / 0 / 25 | `sprints/03-bugs-and-console.md` |
| 04. Событийная модель и модуль Users | Closed | 0 / 0 / 9 | `sprints/04-events-and-users.md` |
| 05. Усиление безопасности и OCR-рефакторинг | Closed | 0 / 0 / 13 | `sprints/05-security-ocr.md` |
| 06. Надёжность диалога и observability | Active | 0 / 0 / 24 | `sprints/06-reliability-and-observability.md` |

> Таблицу обновлять одновременно с переходами статусов в файлах спринтов (см. `process.md` §7.3 и §7.9).

## Ссылки

- [`process.md`](./process.md) — правила работы со спринтами и задачами, легенды, шаблоны, пошаговый алгоритм.
- [`sprints/`](./sprints/) — файлы спринтов.
- [`_docs/instructions.md`](../_docs/instructions.md) — правила разработки (git-дисциплина, стиль, тесты, flake8).
- [`_docs/roadmap.md`](../_docs/roadmap.md) — что планируется (Planned/Backlog), источник кандидатов на новые спринты.
- [`_docs/current-state.md`](../_docs/current-state.md) — фактическое состояние кода `app/`, баги/легаси, нюансы.
