# Спринт 03. Исправление багов и консольный режим

- **Источник:** Обратная связь пользователя (баги, таймауты, картинки, скиллы); `_docs/roadmap.md` Этап 6 (новые адаптеры).
- **Ветка:** `feature/03-bugs-and-console` (от `main`, после закрытия спринта 02).
- **Открыт:** 2026-04-30
- **Закрыт:** —

## 1. Цель спринта

Закрыть критические баги, мешающие использованию: таймауты при `/new` и долгих запросах, неработающие новые скиллы, потеря контекста картинок. Заложить фундамент для мульти-адаптерной архитектуры через консольный режим как «эталонный» адаптер.

## 2. Скоуп и non-goals

### В скоупе
- Диагностика и устранение таймаутов (§1.1, §2.1).
- Поддержка YAML frontmatter в скиллах (§1.4).
- Консольный адаптер с полным набором команд (§2.3).
- Выбор поисковика через команды (§3.1).
- Рекомендации по vision-моделям (§1.3).
- Обработка reply-сообщений в Telegram (§3.3).
- Форматирование кода для Telegram (§3.2).

### Вне скоупа (non-goals)
- Интеграция с внешними онлайн-чатами (GPT-4, Claude) — отдельный спринт.
- Hot-reload моделей (разогрев) — отдельный спринт.
- Web и MAX адаптеры — следующий спринт после консоли.
- Песочница (sandbox) для tools.

## 3. Acceptance Criteria спринта

- [ ] `/new` работает быстро или даёт понятный прогресс, нет таймаутов.
- [ ] Бот принимает новые скиллы (bash-linux, bash-pro, weather) без ошибок.
- [ ] Консольный режим запускается и поддерживает все команды Telegram.
- [ ] Команда для выбора поисковика работает в Telegram и консоли.
- [ ] Reply-сообщения в Telegram обрабатываются с контекстом.
- [ ] Код в ответах бота отформатирован для Telegram.
- [ ] Все задачи спринта — `Done`, сводная таблица актуальна.

---

## 4. Этап 1. Критические баги

Цель — устранить блокеры: таймауты, неработающие скиллы, проблемы с картинками.

### Задача 1.1. Диагностика и устранение таймаутов при `/new` и долгих запросах

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §5; `_docs/commands.md` §`/new`; `_docs/current-state.md`.
- **Затрагиваемые файлы:** `app/services/archiver.py`, `app/services/summarizer.py`, `app/adapters/telegram/handlers/commands.py`, `app/config.py`, `.env.example`.

#### Описание

Проблема: при `/new` долгое выполнение, часто таймаут. То же при долгих запросах агента.

Диагностика:
1. Добавить детальное логирование этапов `/new` (суммаризация, эмбеддинг, запись в БД).
2. Проверить, где теряется время (суммаризация длинных сессий, map-reduce, embedding чанков).

Решения:
- Возможно, `map-reduce` суммаризация создаёт слишком много вызовов LLM — оптимизировать размер батчей.
- Возможно, embedding чанков последовательный — сделать параллельным с ограничением concurrency.
- Возможно, таймаут Ollama слишком мал для больших моделей — добавить параметр таймаута для суммаризации.

#### Definition of Done

- [x] Логирование показывает время каждого этапа `/new` (суммаризация, чанкинг, embedding, запись).
- [x] Оптимизация: embedding чанков параллельный (asyncio.gather с семафором).
- [x] Команда `/new` показывает прогресс пользователю («Суммирую…», «Создаю эмбеддинги…») при длительности > 5 секунд.
- [x] Тест: `/new` на сессии из 50+ сообщений завершается < 30 секунд.
- [x] **Документация обновлена:** `_docs/architecture.md` §5, `_docs/commands.md` §`/new`.
- [x] **Тесты добавлены:** тест параллельного embedding, тест прогресса.
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.2. Проверка и оптимизация схемы SQLite

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §5; `app/services/memory.py`.
- **Затрагиваемые файлы:** `app/services/memory.py`, `tests/services/test_memory.py`.

#### Описание

Проверить таблицу `memory_chunks`: лишние столбцы, foreign keys.

Текущая схема (из кода):
```sql
CREATE TABLE IF NOT EXISTS memory_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    conversation_id TEXT    NOT NULL,
    chunk_index     INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,
    text            TEXT    NOT NULL
);
```

Вопросы:
1. Нужен ли `chat_id` отдельно от `user_id`? В Telegram они связаны, но для других адаптеров — возможно нет.
2. Нужен ли foreign key? sqlite-vec использует `rowid`, связь через него.
3. Нужен ли индекс по `created_at` для старых чанков?

#### Definition of Done

- [x] Проверена схема: `memory_chunks` + `memory_vec` (virtual table).
- [x] Решение: оставить как есть, добавить индекс по `created_at` для future cleanup.
- [x] Код: комментарии по назначению каждого поля.
- [x] **Документация обновлена:** `_docs/memory.md` §3.5 (схема таблиц).
- [x] Тесты: существующие покрывают (зелёный pytest).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.3. Рекомендации по лёгким vision-моделям

- **Статус:** Done
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/current-state.md`; `_docs/architecture.md` §6.4; `app/services/vision.py`.
- **Затрагиваемые файлы:** `_docs/skills.md` или новый `_docs/vision-models.md`, `README.md`.

#### Описание

Рекомендовать лучшие лёгкие vision-модели для Ollama (локальный запуск).

Исследование:
- **moondream2** (~1.6B) — самая лёгкая, быстрая, но качество ниже.
- **llava-phi3** (~4B) — баланс скорости и качества.
- **minicpm-v** (~8B) — хорошее качество, работа с текстом на картинках (OCR).
- **gemma3:4b** — нативно мультимодальная, от Google, 4B параметров.
- **qwen2.5-vl:7b** — лучшее качество для структурированного анализа (таблицы, диаграммы).

Рекомендация по умолчанию: `gemma3:4b` или `llava-phi3`.

#### Definition of Done

- [x] Документ сравнение моделей: размер, скорость, качество, use case.
- [x] Обновить `.env.example`: `VISION_MODEL=gemma3:4b` с пояснением.
- [x] **Документация добавлена:** `_docs/vision-models.md`, ссылка в `_docs/README.md`.
- [x] Тесты: n/a (документация).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.4. Поддержка YAML frontmatter в скиллах

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/skills.md` §3; `app/services/skills.py`.
- **Затрагиваемые файлы:** `app/services/skills.py`, `tests/services/test_skills.py`, `_docs/skills.md`.

#### Описание

Новые скиллы (`bash-linux`, `bash-pro`, `weather`) используют YAML frontmatter:
```yaml
---
name: bash-linux
description: "..."
risk: unknown
source: community
---
```

Старый парсер ожидает `Description:` в первой строке. Нужно поддержать оба формата:
1. Legacy: `Description: <text>` в первой строке.
2. YAML frontmatter: `---
description: "..."
---`.

#### Definition of Done

- [x] `SkillRegistry.load()` парсит оба формата (legacy и YAML frontmatter).
- [x] Для YAML frontmatter: извлекаем `description`, опционально `name`, `risk`, `source`.
- [x] Тест: скилл с YAML frontmatter загружается без ошибок.
- [x] Тест: legacy-скилл (`example-summary`) продолжает работать.
- [x] **Документация обновлена:** `_docs/skills.md` §3 (форматы SKILL.md), `_skills/README.md`.
- [x] **Тесты добавлены:** парсинг YAML frontmatter, fallback на legacy.
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.5. Сохранение контекста картинки для уточняющих вопросов

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.3
- **Связанные документы:** `_docs/architecture.md` §6.4; `app/adapters/telegram/handlers/messages.py`, `app/services/vision.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `app/services/conversation.py`, `_docs/architecture.md`.

#### Описание

Проблема: пользователь кидает картинку, агент описывает её. Пользователь спрашивает «а что там написано в углу?» — агент не понимает, т.к. видит только текстовое описание.

Решения (на выбор, обсудить):
1. **Сохранять base64 картинки в истории** — дорого по токенам, но точно работает.
2. **Сохранять путь к файлу** — временные файлы удаляются, нужно архивирование.
3. **Давать агенту tool для повторного анализа** — агент сам вызовет `describe_image` если нужно.

Выбранный подход: **№3** — добавить tool `describe_image`, который агент может вызвать. При первой загрузке картинки — описание + путь в `tmp/`. Если агенту нужны детали — он вызывает tool с путём.

#### Definition of Done

- [x] Tool `describe_image(image_path: str) -> str` — вызывает `Vision.describe()`.
- [x] Handler `handle_photo` передаёт в `goal` путь к файлу + описание.
- [x] Временные файлы картинок **не удаляются сразу** — живут 1 час (или до `/new`).
- [x] **Документация обновлена:** `_docs/architecture.md` §6.4, `_docs/tools.md`.
- [x] **Тесты добавлены:** tool `describe_image`, handler с путём.
- [x] `git status` чист, `pytest -q` зелёный.

---

## 5. Этап 2. Консольный адаптер

Цель — создать «эталонный» адаптер для работы с агентом без Telegram.

### Задача 2.1. Спецификация консольного режима

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §8.4; `_docs/commands.md`; `_docs/instructions.md` §1.
- **Затрагиваемые файлы:** `_docs/console-adapter.md` (новый), `_docs/architecture.md`.

#### Описание

Спецификация CLI-режима:
- Запуск: `python -m app.console` (отдельная entry point, не `__main__.py`).
- Поддержка всех команд Telegram: `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset` + текст.
- История диалога в памяти (как в Telegram).
- User ID фиксированный (например, `-1` для консоли).
- Выход по `/exit` или Ctrl+D.
- Форматирование: markdown (не HTML как в Telegram).

Архитектура:
- `app/adapters/console/` — пакет консольного адаптера.
- `ConsoleAdapter` класс — аналог `TelegramAdapter`, вызывает `core.handle_user_task`.
- Общие команды вынести в `app/commands/` (shared между Telegram и консолью).

#### Definition of Done

- [ ] Документ `_docs/console-adapter.md` со спецификацией.
- [ ] Обновить `_docs/architecture.md` §8.4 — упомянуть консольный адаптер как пример.
- [ ] Тесты: n/a (документация).
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 2.2. Вынос команд в общий модуль

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.1
- **Связанные документы:** `_docs/console-adapter.md`; `_docs/commands.md`; `app/adapters/telegram/handlers/commands.py`.
- **Затрагиваемые файлы:** `app/commands/__init__.py`, `app/commands/registry.py`, `app/adapters/telegram/handlers/commands.py` (рефакторинг).

#### Описание

Вынести логику команд из `telegram/handlers/commands.py` в общий модуль `app/commands/`:
- `CommandContext` — user_id, chat_id, conversations, archiver, settings и т.д.
- `CommandResult` — текст ответа + флаги (например, `clear_screen`).
- Каждая команда — функция `async def cmd_new(ctx: CommandContext) -> CommandResult`.

Telegram handler вызывает общую команду и отправляет результат через `message.answer()`.
Консольный adapter вызывает ту же команду и печатает в stdout.

#### Definition of Done

- [ ] Модуль `app/commands/` с `CommandContext`, `CommandResult`, `CommandRegistry`.
- [ ] Все команды (`/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset`) вынесены в `app/commands/`.
- [ ] Telegram handler рефакторен: использует `app/commands/`.
- [ ] Тесты для команд работают (обновить `tests/adapters/telegram/test_commands.py`).
- [ ] **Документация обновлена:** `_docs/commands.md` (новая структура), `_docs/architecture.md`.
- [ ] **Тесты добавлены/обновлены:** `tests/commands/test_*.py`.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 2.3. Реализация консольного адаптера

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 2.2
- **Связанные документы:** `_docs/console-adapter.md`; `app/__main__.py`.
- **Затрагиваемые файлы:** `app/adapters/console/__init__.py`, `app/adapters/console/adapter.py`, `app/console_main.py`.

#### Описание

Реализовать консольный адаптер:
- `app/adapters/console/adapter.py` — `ConsoleAdapter` класс.
- `app/console_main.py` — точка входа `python -m app.console`.
- REPL цикл: читает строку → парсит команду/текст → вызывает `core.handle_user_task` → печатает ответ.
- Поддержка истории (readline/arrow keys) через `readline` модуль.
- Graceful shutdown по Ctrl+C / Ctrl+D.

#### Definition of Done

- [ ] `python -m app.console` запускается и работает REPL.
- [ ] Все команды `/start`, `/help`, `/models`, `/model`, `/prompt`, `/new`, `/reset` работают.
- [ ] Текстовые сообщения обрабатываются через `core.handle_user_task`.
- [ ] История между сообщениями сохраняется (in-memory).
- [ ] **Документация обновлена:** `_docs/console-adapter.md`, `_docs/README.md` (навигация).
- [ ] **Тесты добавлены:** `tests/adapters/console/test_adapter.py` (моки stdin/stdout).
- [ ] `git status` чист, `pytest -q` зелёный.

---

## 6. Этап 3. Поисковик и форматирование

Цель — дать пользователю выбор поисковика и красивый вывод кода.

### Задача 3.1. Выбор поисковика через команды

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** Задача 2.2
- **Связанные документы:** `_docs/commands.md`; `_docs/stack.md` §9; `app/tools/web_search.py`.
- **Затрагиваемые файлы:** `app/config.py`, `app/commands/search_engine.py`, `app/tools/web_search.py`, `.env.example`.

#### Описание

Команды `/search_engines` (список) и `/search_engine <name>` (выбор активного).
Поисковики: `duckduckgo` (default), `bing`, `google` (требует API ключ), `brave`, `searxng`.

Хранение: `UserSettingsRegistry` (in-memory, как модель и системный промпт).
Tool `web_search` читает активный поисковик из контекста.

#### Definition of Done

- [ ] Команды `/search_engines`, `/search_engine <name>` в `app/commands/`.
- [ ] `UserSettingsRegistry` поддерживает `search_engine` per user.
- [ ] Tool `web_search` использует активный поисковик (fallback на `duckduckgo`).
- [ ] **Документация обновлена:** `_docs/commands.md` §«Выбор поисковика», `_docs/stack.md` §9.
- [ ] **Тесты добавлены:** команды, tool с разными поисковиками.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 3.2. Форматирование кода для Telegram

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/commands.md`; `app/adapters/telegram/handlers/messages.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/utils.py`, `app/adapters/telegram/handlers/messages.py`.

#### Описание

Когда агент возвращает код, оборачивать в Telegram-специфичное форматирование:
- Кодовые блоки markdown → HTML: ` ```python\n...\n``` ` → `<pre><code class="language-python">...</code></pre>`.
- Или использовать `ParseMode.MARKDOWN` для ответов с кодом.

Утилита `format_for_telegram(text: str) -> tuple[str, ParseMode]` — определяет, есть ли код, и выбирает parse_mode.

#### Definition of Done

- [ ] Утилита `format_for_telegram` в `app/adapters/telegram/utils.py`.
- [ ] Handler `messages.py` использует утилиту для выбора `ParseMode`.
- [ ] Код в ответах отображается с подсветкой синтаксиса в Telegram.
- [ ] **Документация обновлена:** `_docs/commands.md` (раздел «Форматирование»).
- [ ] **Тесты добавлены:** `tests/adapters/telegram/test_utils.py`.
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 3.3. Обработка reply-сообщений в Telegram

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md` §4; `app/adapters/telegram/handlers/messages.py`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `tests/adapters/telegram/test_messages.py`.

#### Описание

Когда пользователь нажимает «Ответить» на сообщение — включать текст оригинального сообщения в контекст.

Формат:
```
[В ответ на: <текст оригинального сообщения>]
<текст ответа пользователя>
```

Если оригинал — длинный, обрезать до N символов.

#### Definition of Done

- [ ] Handler `handle_text` проверяет `message.reply_to_message`.
- [ ] Если есть reply — добавляет контекст оригинального сообщения.
- [ ] **Документация обновлена:** `_docs/architecture.md` §4, `_docs/commands.md`.
- [ ] **Тесты добавлены:** reply с текстом, reply с длинным текстом (обрезка).
- [ ] `git status` чист, `pytest -q` зелёный.

---

## 7. Этап 4. Аудит и техдолг после Этапов 1–3

Цель — закрыть мелкие огрехи и рассинхронизации, накопившиеся за Этапы 1–3 этого спринта и за Этапы 3–5 спринта 02. Не критично для пользователя, но мешает дальнейшей разработке: ломаются перекрёстные ссылки, агент видит часть промпта на английском, новые скиллы непереведённые, дефолт vision-модели разный в коде и доке.

### Задача 4.1. Перенумерация `_docs/architecture.md` и сломанные кросс-ссылки

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md`; `_docs/commands.md`; `app/adapters/telegram/handlers/errors.py`.
- **Затрагиваемые файлы:** `_docs/architecture.md`, `_docs/commands.md`, `app/adapters/telegram/handlers/errors.py`, `tests/adapters/telegram/test_errors.py`, `_board/sprints/03-bugs-and-console.md`.

#### Описание

После Этапа 3 спринта 02 в `_docs/architecture.md` вставили секцию §6 «Поток обработки файлов», но не сдвинули нумерацию остальных. Получилось:

- §6 «Поток обработки файлов» (новая)
- §7 «Обработка ошибок» (была §6)
- §7 «Расширяемость» (была §7) ← **дубликат номера**
- §8 «Конкурентность», §9, §10 ← всё на единицу не сдвинуто

Кроме этого:

- В §3.2 и §6.4 `VISION_MODEL` указана как default `None`, пример `llava:7b`. После задачи 03.1.3 в `.env.example` стоит `VISION_MODEL=gemma3:4b`. Рассинхронизация.
- В §10 «Что архитектура **не делает**» пункт «Не парсит мультимодальный ввод (фото / аудио / документы) в MVP» противоречит реализации Этапа 3 спринта 02.
- Кросс-ссылки на старую нумерацию `§6` (про обработку ошибок) живут в `app/adapters/telegram/handlers/errors.py`, `tests/adapters/telegram/test_errors.py`, `_docs/commands.md` (по поиску `architecture.md` §6).
- Кросс-ссылка на `§7.4` (web/MAX-адаптеры) живёт в этом же файле спринта, в Задаче 2.1 — после перенумерации станет §8.4.

#### Definition of Done

- [x] В `_docs/architecture.md` устранена двойная нумерация: «Расширяемость» → §8, «Конкурентность» → §9, «Точки наблюдаемости» → §10, «Что архитектура не делает» → §11. Подсекции §7.1–§7.5 → §8.1–§8.5.
- [x] В §3.2 и §6.4 указано `VISION_MODEL` (default `gemma3:4b`) с ссылкой на `_docs/vision-models.md`.
- [x] В §11 убран пункт «Не парсит мультимодальный ввод», заменён на «Не работает с видео и стримами медиа».
- [x] Кросс-ссылки на старую нумерацию `§6` (обработка ошибок) исправлены в `app/adapters/telegram/handlers/errors.py`, `tests/adapters/telegram/test_errors.py`, `_docs/commands.md`. Дополнительно исправлены ссылки `§7` в `_docs/architecture.md` §2 и `_docs/requirements.md` NFR-10.
- [x] Кросс-ссылка `§7.4` → `§8.4` исправлена в этом же файле спринта (Задача 2.1) и в `_docs/roadmap.md` (Этап 6).
- [x] **Документация обновлена**.
- [x] Тесты: n/a (контент только в `_docs/`, докстрингах и комментарии).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 4.2. Заполнить `_board/README.md`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/README.md`; `_board/plan.md`; `_board/process.md`; `_board/progress.txt`.
- **Затрагиваемые файлы:** `_board/README.md`.

#### Описание

`_board/README.md` пустой (1 байт), хотя `_docs/README.md` указывает его как точку входа для нового LLM-агента: «`CLAUDE.md` → `_docs/README.md` → `_board/README.md` → `_board/plan.md` → ...». Нужно лаконично описать, что лежит в `_board/`, и направить читателя дальше.

#### Definition of Done

- [x] `_board/README.md` содержит: краткое назначение каталога, состав (`plan.md`, `process.md`, `progress.txt`, `sprints/`), порядок чтения, явное разграничение `_board/` vs `_docs/`.
- [x] Тесты: n/a (документация).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 4.3. Чистка сломанных ссылок на `CLAUDE.md` в `instructions.md` и `process.md`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `CLAUDE.md`; `_docs/instructions.md`; `_board/process.md`.
- **Затрагиваемые файлы:** `_docs/instructions.md`, `_board/process.md`.

#### Описание

После замены `CLAUDE.md` на перевод гайдлайнов Karpathy (§1 «Сначала думай», §2 «Минимализм», §3 «Хирургические правки», §4 «Выполнение от цели») остались две сломанные ссылки:

- `_docs/instructions.md` §1, абзац про ритуал коммитов: «Подробно — в `CLAUDE.md` §4 и `_board/process.md`». В `CLAUDE.md` §4 — про «Выполнение от цели», не про коммиты. Нужно убрать ссылку на `CLAUDE.md`, оставить `_board/process.md` (§3, §8, §9).
- `_board/process.md` §«Чек-лист перед переходом к следующей задаче»: «**Документация обновлена ...** (см. CLAUDE.md §0)». В `CLAUDE.md` нет §0. Заменить на ссылку на `_docs/instructions.md` §8 «Документация».

Ссылки `CLAUDE.md §3` и `CLAUDE.md §2` в `_docs/instructions.md` §10 — корректные (§3 «Хирургические правки», §2 «Минимализм»), не трогаем.

#### Definition of Done

- [x] В `_docs/instructions.md` §1 ссылка на `CLAUDE.md §4` убрана, оставлена только `_board/process.md` (§3, §8, §9).
- [x] В `_board/process.md` чек-лист — ссылка на `CLAUDE.md §0` заменена на `_docs/instructions.md` §8.
- [x] Тесты: n/a (документация).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 4.4. Перевод community-скиллов на русский

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/skills.md` §3; `_skills/README.md`.
- **Затрагиваемые файлы:** `_skills/bash-linux/SKILL.md`, `_skills/bash-pro/SKILL.md`, `_skills/weather/SKILL.md`.

#### Описание

После задачи 03.1.4 (YAML frontmatter) в `_skills/` появились три community-скилла из внешних источников: `bash-linux`, `bash-pro`, `weather`. Все три — на английском, включая `description`, который попадает в системный промпт агента на каждом ходе через `{{SKILLS_DESCRIPTION}}`. По правилу `_docs/instructions.md` §0 язык проекта — русский (с латиницей в именах команд / флагов / технических идентификаторов).

Подход: переводим заголовки секций, описания и пояснения. Имена bash-команд / curl-аргументов / флагов остаются латиницей — это технические идентификаторы.

#### Definition of Done

- [x] В трёх скиллах `description` (внутри YAML frontmatter) — на русском, ≤ 200 символов, с явным триггером.
- [x] Заголовки и пояснения в теле — на русском.
- [x] Имена команд (`grep`, `curl`, `lsof`, флаги, аргументы wttr.in) — латиницей (это код, не текст).
- [x] `bash-pro` сокращён с 320 до ~140 строк, убраны шаблонные community-секции, добавлено примечание про отсутствие shell-tool в проекте.
- [x] Smoke: `SkillRegistry.load()` возвращает все 4 скилла (bash-linux, bash-pro, example-summary, weather) с русскими описаниями.
- [x] **Документация обновлена** (`_skills/README.md` — n/a, шаблоны там общие).
- [x] Тесты: n/a (контент скиллов).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 4.5. Русификация логов и сообщений ошибок

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/instructions.md` §1, §6.
- **Затрагиваемые файлы:** `app/services/vision.py`, `app/services/transcribe.py`, `app/adapters/telegram/handlers/messages.py`, `app/tools/read_document.py`, при необходимости — соответствующие тесты.

#### Описание

В коде, добавленном на Этапе 3 спринта 02, логи и `ToolError`-сообщения остались на английском. По §0 язык проекта — русский (структурные поля и идентификаторы — латиницей).

Конкретно:

- `app/services/vision.py`: `Describing %s with model=%s caption=%s`, `Failed to read image %s: %s`, `Vision description complete: %d chars`, `Vision description failed: %s`.
- `app/services/transcribe.py`: `Transcribing %s with model=%s language=%s`, `Transcription complete: %d chars`.
- `app/adapters/telegram/handlers/messages.py`: ~17 строк `logger.warning/error/info` (`LLM timeout`, `LLM unavailable`, `LLM bad response`, `in-session summary failed`, `File too large`, `Voice too large`, `Photo too large`, `Failed to delete tmp file`, `Vision model not configured`, `LLM not available for vision`, `Transcriber unavailable`, `Transcriber initialization failed`, `Transcription failed`, `Vision description failed`, `Download failed`, `Failed to delete tmp voice file`, `Failed to delete tmp photo file`).
- `app/tools/read_document.py`: 8 `ToolError`-сообщений (`path not allowed`, `path resolve error`, `file not found`, `not a regular file`, `pypdf not installed`, `unsupported file type`, `PDF read error`, `file is not valid UTF-8 text`, `file read error`). Уходят как `observation` агенту, который должен видеть их по-русски.

Структурные поля логов (`user=`, `dur_ms=`, `model=`, `tool=`) и URI / mime-types остаются латиницей.

#### Definition of Done

- [x] Логи в `vision.py` (4 строки), `transcribe.py` (2 строки), `messages.py` (~17 строк) переведены на русский, структурные поля (`user=`, `model=`, `caption=`, `size=`) сохранены латиницей.
- [x] 9 `ToolError`-сообщений в `read_document.py` переведены на русский.
- [x] Assertions в `tests/adapters/telegram/test_messages.py` (2 шт) и `tests/tools/test_read_document.py` (5 шт) обновлены под русский текст.
- [x] **Документация обновлена**: n/a (правило в `_docs/instructions.md` §0/§5 уже зафиксировано).
- [x] Тесты: `pytest -q` зелёный (256 passed).
- [x] `git status` чист.

---

### Задача 4.6. Мелкие правки кода `archiver.py` и `files.py`

- **Статус:** Done
- **Приоритет:** low
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/instructions.md` §3 (стиль), §4 (async).
- **Затрагиваемые файлы:** `app/services/archiver.py`, `app/adapters/telegram/files.py`.

#### Описание

Найдены два мелких огреха стиля, не критичных, но нарушающих правила проекта:

1. `app/services/archiver.py:69`: type-hint `progress_callback: "callable[[str], Any] | None" = None` — `callable` с маленькой буквы. Должен быть `Callable` из `collections.abc` (или `typing`). Сейчас не падает только потому что строковая forward-reference и никем не валидируется.
2. `app/services/archiver.py:81-86`: внутри `_notify` повторный `import asyncio`, хотя `asyncio` уже импортирован сверху файла.
3. `app/adapters/telegram/files.py:94`: `import uuid` внутри тела функции `download_telegram_file`. По §2 импорты должны быть в начале файла.

#### Definition of Done

- [x] `archiver.py`: type-hint `progress_callback` — `Callable[[str], Awaitable[None] | None] | None` с импортом из `typing`. `Any` убран из импорта как осиротевший.
- [x] `archiver.py`: убран лишний `import asyncio` внутри `_notify`.
- [x] `files.py`: `import uuid` поднят в верхушку файла.
- [x] Тесты: `pytest -q` зелёный (256 passed; правки чисто стилистические).
- [x] `git status` чист.

---

### Задача 4.7. Реорганизация документации `_board/` и `_docs/instructions.md`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_board/plan.md`; `_board/process.md`; `_board/README.md`; `_docs/instructions.md`; `_docs/project-structure.md`; `_docs/README.md`.
- **Затрагиваемые файлы:** `_board/plan.md`, `_board/process.md`, `_board/README.md`, `_docs/instructions.md`, `_docs/project-structure.md`, `_docs/README.md`.

#### Описание

`_board/plan.md` разросся: в нём лежат легенда статусов, правила работы со спринтами и задачами, шаблоны файла спринта и задачи. Это делает `plan.md` не индексом, а документом с правилами; плюс часть этого материала дублируется в `_board/process.md`. Аналогично в `_docs/instructions.md` §1 и §9 частично пересекаются с `process.md`.

Образец — проект `fine-tuning/` (`_board/plan.md` содержит только индекс спринтов, все правила/легенды/шаблоны живут в `_board/process.md`).

Цели:

1. Сделать `_board/process.md` **единым статичным документом с правилами** — легенды статусов (задач и спринтов), приоритеты, объём, правила работы со спринтами и задачами, шаблоны, пошаговый процесс открытия/выполнения/закрытия. Любой ИИ или человек должен открыть `process.md` и получить полный набор правил для единообразного заполнения документации.
2. Сделать `_board/plan.md` **минимальным индексом** — только таблицы активных/закрытых/запланированных спринтов и ссылки.
3. Убрать дубли из `_docs/instructions.md` (ритуал коммитов, процесс фичи) — заменить ссылками на `process.md`.
4. Перенумеровать `process.md` с §1 (текущая нумерация начинается с §0, что некрасиво). Обновить все кросс-ссылки в репозитории.
5. Добавить недостающие правила из примера `fine-tuning/`: таблица приоритетов, таблица объёмов, явное упоминание обновления `progress.txt`.
6. Пройти по закрытым спринтам — **не трогать** исторические ссылки на `_board/plan.md § «Шаблон файла спринта»` (они — часть истории, закрытые спринты неизменны).

#### Definition of Done

- [x] `_board/process.md` содержит: легенды (статусы задач, статусы спринтов, приоритеты, объём), правила работы со спринтами, правила работы с задачами, шаблоны (файл спринта, задача), процессы (подготовка к сессии, открытие спринта, выполнение задачи, обновление документации, обновление `progress.txt`, закрытие спринта), чек-лист и TL;DR. Нумерация начинается с §1.
- [x] `_board/plan.md` содержит только индекс спринтов (активные, закрытые, запланированные) и ссылки на `process.md` и `_docs/instructions.md`.
- [x] В `_docs/instructions.md` §2 (Git-дисциплина) и §10 (Процесс добавления фичи) нет прямых дублей правил из `process.md` — только ссылки; §-ссылки обновлены под новую нумерацию `process.md`. Сам `instructions.md` перенумерован с §1 (было с §0).
- [x] В `_board/README.md` ссылки на `process.md` обновлены под новую нумерацию.
- [x] В `_docs/project-structure.md` описания `plan.md` и `process.md` обновлены под новую ответственность.
- [x] В `_docs/README.md` порядок чтения не сломан (точка входа `CLAUDE.md → … → _board/plan.md → _board/sprints/<active>.md → _board/process.md` остаётся валидной).
- [x] Закрытые спринты (`sprints/00-*`, `sprints/01-*`, `sprints/02-*`) — **не тронуты** (правило «история неизменна»).
- [x] Живые кросс-ссылки на `instructions.md §X` обновлены: `_docs/links.md`, `app/adapters/telegram/handlers/commands.py`, «Связанные документы» задач 2.1, 4.5, 4.6 в спринте 03.
- [x] В `_board/process.md` §8 добавлены правила работы с `_docs/current-state.md` и `_docs/roadmap.md` (когда читать, когда обновлять, что не пишем); зафиксирована роль каждого документа.
- [x] `_docs/roadmap.md` перенумерован с §1 (было с §0): Этап 0 → 1, …, Этап 15 → 16; добавлены статусы этапов (`Closed`/`Active`/`Planned`/`Backlog`), уточнена роль документа. Актуализирован Этап 1 (Bootstrap) и Этап 2 (MVP Agent) — Closed; Этап 8 (Файловые входы) — Closed по части Спринта 02.
- [x] `_docs/current-state.md` — уточнена роль и связь с `roadmap.md` / `_board/plan.md`, отсылка к `process.md` §8.2.
- [x] Живые ссылки на номера этапов roadmap синхронизированы в: `_docs/mvp.md`, `_docs/agent-loop.md`, `_docs/tools.md`, `_docs/requirements.md`, `_prompts/README.md`, `_skills/README.md`, `_skills/example-summary/SKILL.md`, `app/core/orchestrator.py`, `_board/plan.md`, активный спринт 03 (источник, задача 4.1 DoD). Закрытые спринты 00/01/02 не тронуты (история).
- [x] Корневой `README.md` актуализирован: дефолтная vision-модель — `gemma3:4b` (синхронизировано с `.env.example` и `_docs/vision-models.md`); ссылки на `_docs/README.md`, `_board/README.md`, `_skills/README.md`, `_prompts/README.md` проверены — актуальны.
- [x] Тесты: n/a (документация).
- [x] `pytest -q` зелёный (255 passed), `git status` чист.

---

## 8. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Консольный адаптер затягивается по срокам | Разбить на задачи 2.1–2.3, можно остановиться после 2.2 (инфраструктура) |
| 2 | Таймауты `/new` требуют архитектурных изменений | Начать с диагностики (логирование), потом оптимизация |
| 3 | YAML frontmatter сломает существующие скиллы | Поддержать оба формата, тесты на оба |
| 4 | Сохранение картинок занимает много места | TTL 1 час + cleanup job, ограничение размера tmp/ |

---

## 9. Сводная таблица задач спринта

| #   | Задача | Приоритет | Объём | Статус | Зависит от |
|-----|--------|:---------:|:-----:|:------:|:----------:|
| 1.1 | Диагностика и устранение таймаутов | high | M | Done | — |
| 1.2 | Проверка схемы SQLite | high | S | Done | — |
| 1.3 | Рекомендации vision-моделей | high | XS | Done | — |
| 1.4 | Поддержка YAML frontmatter | high | S | Done | — |
| 1.5 | Контекст картинки для уточнений | high | M | Done | 1.3 |
| 2.1 | Спецификация консольного режима | high | S | ToDo | — |
| 2.2 | Вынос команд в общий модуль | high | M | ToDo | 2.1 |
| 2.3 | Реализация консольного адаптера | high | M | ToDo | 2.2 |
| 3.1 | Выбор поисковика | medium | S | ToDo | 2.2 |
| 3.2 | Форматирование кода | medium | XS | ToDo | — |
| 3.3 | Обработка reply | medium | S | ToDo | — |
| 4.1 | Перенумерация architecture.md и кросс-ссылки | high | S | Done | — |
| 4.2 | Заполнить `_board/README.md` | medium | XS | Done | — |
| 4.3 | Чистка ссылок на CLAUDE.md в instructions.md/process.md | medium | XS | Done | — |
| 4.4 | Перевод community-скиллов на русский | medium | S | Done | — |
| 4.5 | Русификация логов и ToolError | medium | S | Done | — |
| 4.6 | Мелкие правки `archiver.py` и `files.py` | low | XS | Done | — |
| 4.7 | Реорганизация документации `_board/` и `instructions.md` | medium | S | Done | — |

---

## 10. История изменений спринта

- **2026-04-30** — спринт открыт, ветка `feature/03-bugs-and-console` создана от `main`.
- **2026-04-30** — задача 1.1 Done: диагностика и устранение таймаутов `/new` (логирование этапов, параллельный embedding, progress callback, EMBEDDING_CONCURRENCY).
- **2026-04-30** — задача 1.2 Done: проверка схемы SQLite (индекс по created_at, комментарии к полям).
- **2026-04-30** — задача 1.3 Done: рекомендации по vision-моделям (gemma3:4b по умолчанию, сравнительная таблица моделей).
- **2026-04-30** — задача 1.4 Done: поддержка YAML frontmatter в скиллах (bash-linux, bash-pro, weather), обратная совместимость с legacy форматом.
- **2026-05-03** — открыт Этап 4 «Аудит и техдолг после Этапов 1–3»: добавлены задачи 4.1–4.6 (перенумерация architecture.md, README в `_board/`, ссылки на CLAUDE.md, перевод скиллов, русские логи, мелкие правки кода).
- **2026-05-03** — задача 4.1 Done: architecture.md §7 (двойной) → §8, кросс-ссылки §6→§7 в errors.py/test_errors.py/commands.md, §7.4→§8.4 в roadmap.md и спринте 03 (задача 2.1), синхронизация VISION_MODEL=gemma3:4b в architecture.md §3.2/§6.4.
- **2026-05-03** — задача 4.2 Done: заполнен `_board/README.md` (навигация по plan/process/progress/sprints, разграничение `_board/` vs `_docs/`).
- **2026-05-03** — задача 4.3 Done: убраны сломанные ссылки на `CLAUDE.md` §4/§0 в `_docs/instructions.md` §1 и `_board/process.md` чек-листе.
- **2026-05-03** — задача 4.4 Done: community-скиллы `bash-linux`, `bash-pro`, `weather` переведены на русский (технические идентификаторы остаются латиницей); `bash-pro` сокращён с 320 до ~140 строк.
- **2026-05-03** — задача 4.5 Done: логи vision/transcribe/messages и ToolError-сообщения read_document переведены на русский, структурные поля сохранены латиницей; assertions в тестах обновлены.
- **2026-05-03** — задача 4.6 Done: archiver.py — исправлена аннотация progress_callback (Callable из typing), убраны лишний import asyncio и осиротевший Any; files.py — import uuid поднят наверх.
- **2026-05-04** — открыта задача 4.7 «Реорганизация документации `_board/` и `_docs/instructions.md`»: перенос правил/легенд/шаблонов из `plan.md` в `process.md`, перенумерация `process.md` с §1, чистка дублей в `instructions.md`, синхронизация кросс-ссылок.
- **2026-05-04** — задача 4.7 Done: `plan.md` сведён к индексу спринтов (активные/закрытые/запланированные); `process.md` собран в 13 пронумерованных секций с §1 (легенды, правила спринтов/задач, шаблоны, подготовка, открытие, выполнение, доки, progress, закрытие, переход, чек-лист, TL;DR); добавлены легенды приоритетов и объёмов задач; `instructions.md` перенумерован с §1 (было с §0), дубли процесса в §2/§10 заменены ссылками на `process.md` §7; `_board/README.md` и `_docs/project-structure.md` обновлены под новую структуру. Живые §-ссылки на `instructions.md` синхронизированы в `_docs/links.md`, `app/adapters/telegram/handlers/commands.py` и в активных задачах спринта 03. Закрытые спринты 00/01/02 не тронуты. Дополнительно: в `process.md` §8 добавлены правила работы с `_docs/current-state.md` и `_docs/roadmap.md` (роли, когда читать/обновлять); `_docs/roadmap.md` перенумерован с §1 (Этап 0→1, …, 15→16), добавлены статусы этапов; `_docs/current-state.md` уточнён по роли; ссылки на номера этапов синхронизированы в `_docs/mvp.md`, `_docs/agent-loop.md`, `_docs/tools.md`, `_docs/requirements.md`, `_prompts/README.md`, `_skills/README.md`, `_skills/example-summary/SKILL.md`, `app/core/orchestrator.py`, `_board/plan.md`, спринте 03; корневой `README.md` синхронизирован с дефолтом `VISION_MODEL=gemma3:4b`.
- **2026-05-04** — задача 1.5 Done: добавлен tool `describe_image` для повторного описания изображений по пути; `handle_photo` передаёт путь к файлу + описание в goal; временные файлы картинок не удаляются сразу — живут 1 час или до `/new` (cleanup в cmd_new); обновлена документация `tools.md` §4.7 и `architecture.md` §6.4; добавлены тесты для `describe_image`.
