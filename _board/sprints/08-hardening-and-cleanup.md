# Спринт 08. Hardening и зачистка техдолга после спринтов 03–05

- **Источник:** ревизия закрытых спринтов 03/04/05 (запрос пользователя 20.05.2026); `_docs/current-state.md` §1.7 (legacy `file_contexts.db`); пробелы в acceptance criteria спринта 05 (Этап 6 — безопасные defaults) и спринта 04 (`UserRepository` без персистентности); рабочая правка `app/main.py` (top-level логирование необработанных исключений) от 21.05.2026.
- **Ветка:** `feature/08-hardening-and-cleanup` (создана от `main` после закрытия спринта 07; см. `_board/process.md` §2 п.1, п.2).
- **Открыт:** 2026-05-21
- **Закрыт:** —

## 1. Цель спринта

Спринты 03–05 закрыли функциональные пробелы (баги, консольный режим, события, безопасность, OCR), но оставили **четыре системных промаха**, замеченных при ревизии:

1. **Безопасность по умолчанию выключена.** В спринте 05 (задача 6.1, риск 4) сознательно зафиксировано: «По умолчанию allowlist пустой (все разрешены) для MVP». На сегодня это значит, что опасные tools (`http_request`, `read_file`, `read_document`) исполняются без allowlist-проверки у любого пользователя «из коробки». Цель — переключить дефолт на «secure by default»: пустой allowlist = запрет, явное разрешение через `.env`.
2. **`InputSanitizer` / `ResponseSanitizer` слабо покрыты тестами.** Спринт 05 (задачи 3.1, 7.1) проверил только базовые паттерны. Нет регрессий на типичные обходы (регистр, разрывы, unicode-эскейпы, base64).
3. **`UserRepository` теряет состояние при рестарте.** Спринт 04 сознательно ограничился in-memory (§2 non-goal), но после спринта 06 (`dialog_journal` хранит `user.id`) рассинхрон стал реальным: после рестарта новый telegram-пользователь получит свободный `user.id`, журналы прежних сессий «потеряют владельца».
4. **Legacy `file_contexts.db` висит в репозитории.** В спринте 06 контекст файлов мигрирован в `dialog_journal`, но `_docs/current-state.md` §1.7 фиксирует: «сохранён только для одноразовой миграции». Файл БД и миграционный код — кандидаты на удаление.
5. **Необработанные исключения на верхнем уровне не логируются.** `app/main.py::run` и `app/console_main.py::run` оборачивают `asyncio.run(main())` без `try/except`. При падении на этапе сборки зависимостей или после остановки polling traceback уходит в stderr без структурного JSON-лога и без отправки в Sentry/GlitchTip (handler настраивается в `setup_sentry`, но `sys.excepthook` не повешен). Цель — пробросить такие исключения в стандартный logger перед re-raise.

Спринт сознательно ограничен зачисткой и hardening'ом — никаких новых фич. Поведение для пользователя меняется минимально (только дефолт безопасности и top-level лог при крэше).

## 2. Скоуп и non-goals

### В скоупе

- Перевод `dangerous_tools_allowlist` в режим «secure by default» с миграцией для существующих пользователей (явный список в `.env.example`).
- Расширение тестов `InputSanitizer` / `ResponseSanitizer` bypass-кейсами; добавление случаев в `tests/security/`.
- Персистентность `UserRepository` через новую таблицу `users` в существующей `data/memory.db` (одно соединение с `SemanticMemory` / `DialogJournal`).
- Удаление миграционного кода `app/services/file_contexts_migration.py` и БД-файла `data/file_contexts.db` после подтверждения, что нет производственных установок без миграции.
- Регрессионный тест на длительность `/new` (DoD задачи 03.1.1: «< 30 секунд на 50+ сообщений» проверялся вручную, регрессии нет).
- Документация: `_docs/security.md`, `_docs/current-state.md`, `_docs/memory.md`, `_docs/instructions.md` (упоминание secure-by-default).
- Логирование необработанных исключений на верхнем уровне в обеих точках входа (`app/main.py`, `app/console_main.py`).

### Вне скоупа (non-goals)

- Любые multi-agent изменения (это спринт 07).
- Новый LLM-провайдер / web-адаптер / MAX-адаптер (`_docs/roadmap.md` Этапы 4–6).
- Полный CI с матрицей версий Python / coverage gate (минимальный CI уже добавлен спринтом 06).
- Изменение формата `memory_chunks` / `dialog_journal`.
- Миграция `UserSettingsRegistry` на персистентное хранилище — отдельная задача (in-memory live override приемлем как кеш).

## 3. Acceptance Criteria спринта

- [x] При пустом `DANGEROUS_TOOLS_ALLOWLIST` в `.env` опасные tools (`http_request`, `read_file`, `read_document`) **запрещены**; чтобы разрешить — нужно явно перечислить их в `.env`. Обновлены `.env.example` и `_docs/security.md`.
- [x] `tests/security/test_input_sanitizer.py` и `tests/security/test_response_sanitizer.py` содержат bypass-кейсы (минимум: разный регистр, разрывы пробелами/неразрывными пробелами, юникод-эскейпы вида `\u0069gnore`, base64-кодированные паттерны как сырая строка), все зелёные.
- [x] `UserRepository` сохраняет пользователей в SQLite (одно соединение с `SemanticMemory`/`DialogJournal`); после рестарта `get_or_create(channel, external_id)` возвращает того же `user.id`, что и до рестарта.
- [x] `data/file_contexts.db` и `app/services/file_contexts_migration.py` удалены; `_docs/current-state.md` §1.7 обновлён; `grep` по репозиторию не находит активных ссылок на `file_contexts.db`.
- [x] Регрессионный тест `tests/services/test_archiver.py::test_archive_completes_within_budget` (или эквивалент) проверяет, что `Archiver.archive` на синтетической сессии из 50 сообщений завершается за фиксированный бюджет с мок-LLM.
- [x] Top-level wrapper `run()` в `app/main.py` и `app/console_main.py` логирует необработанные исключения через `logger.exception(...)` и пробрасывает их дальше; `KeyboardInterrupt` пробрасывается без лога.
- [x] `pytest -q` и `flake8 app tests` зелёные.
- [x] Все задачи спринта — `Done`, сводная таблица актуальна.

## 4. Этап 1. Secure-by-default для опасных tools

Закрываем главный риск из спринта 05 — отключённую по умолчанию защиту.

### Задача 1.1. Сменить дефолт `dangerous_tools_allowlist` на «запрет»

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/security.md`, `_docs/tools.md`, `_board/sprints/05-security-ocr.md` Задача 6.1.
- **Затрагиваемые файлы:** `app/config.py`, `app/tools/registry.py`, `.env.example`, `_docs/security.md`, `tests/tools/test_registry.py`.

#### Описание

1. В `Settings` определить смысл `dangerous_tools_allowlist`: пустой список (или отсутствие переменной) → **запрет** всех tools из списка `DANGEROUS_TOOLS`. Чтобы разрешить — нужно явно перечислить в `.env`.
2. В `.env.example` добавить закомментированную строку `# DANGEROUS_TOOLS_ALLOWLIST=http_request,read_file,read_document` с поясняющим комментарием (по умолчанию — запрет, раскомментировать на свой страх и риск).
3. В `ToolRegistry.execute` логировать `WARNING` при отказе с указанием tool и причиной.
4. **Миграция** для существующих пользователей: на старте бота — если переменной нет в `.env`, вывести в лог `INFO` подсказку, что для обратной совместимости можно временно выставить allowlist со всеми тремя tools.

#### Definition of Done

- [x] `tests/tools/test_registry.py` покрывает: пустой allowlist + dangerous tool → `ToolError`; явный allowlist разрешает; неопасный tool (например, `weather`) всегда разрешён; добавлен отдельный тест `test_dangerous_tool_block_logs_warning`.
- [x] `.env.example` и `_docs/security.md` обновлены; добавлена краткая инструкция «как мигрировать» в `_docs/current-state.md` §6.3.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

### Задача 1.2. Bypass-тесты для `InputSanitizer` и `ResponseSanitizer`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/security.md`, `_board/sprints/05-security-ocr.md` Задачи 3.1, 7.1.
- **Затрагиваемые файлы:** `tests/security/test_input_sanitizer.py`, `tests/security/test_response_sanitizer.py`, при необходимости — `app/security/input_sanitizer.py` / `app/security/response_sanitizer.py` для адаптации паттернов.

#### Описание

Расширить покрытие до bypass-кейсов:

1. Разный регистр: `IGNORE all PREVIOUS instructions`, `IgNoRe AlL pReViOuS iNsTrUcTiOnS`.
2. Разрывы пробелами/неразрывными пробелами: `ignore  all  previous`, `ignore\u00a0all\u00a0previous`.
3. Юникод-эскейпы как сырая строка: `\u0069gnore all previous`.
4. Base64-кодированные паттерны как сырая строка (sanity-check: НЕ декодируем, документируем как known limitation).
5. Для `ResponseSanitizer`: пути с разделителем `\` (Windows-стиль) в логах; пути с `~/`.

Каждый кейс — либо проходит (паттерн расширен), либо явно зафиксирован как known-limitation в `_docs/security.md` с TODO. Цель — не «всё ловить», а **закрыть слепые зоны на будущее**.

#### Definition of Done

- [x] Параметризованный тест `pytest.mark.parametrize` на 8 bypass-кейсов для каждого санитайзера + отдельные тесты на known-limitations.
- [x] Паттерны, которые тесты ловят, — работают без правки кода (`re.IGNORECASE` + `\s+` покрывают регистр/пробелы/NBSP); не ловят (юникод-эскейп, base64, `~/file`, относительные пути) — задокументированы в `_docs/security.md` §5.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 5. Этап 2. Персистентность `UserRepository`

Закрываем системный пробел спринта 04: рассинхрон с `dialog_journal`.

### Задача 2.1. SQLite-реализация `UserRepository` с миграцией

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` (схема `data/memory.db`), `_docs/architecture.md` §3 (Users), `_docs/current-state.md` §1.5, `_docs/events.md` (UserCreated).
- **Затрагиваемые файлы:** `app/users/repository.py`, `app/services/memory.py` (расшаривание SQLite-соединения), `app/main.py`, `app/console_main.py`, `tests/users/test_repository.py`, `_docs/memory.md`.

#### Описание

1. Завести таблицу `users(id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, external_id TEXT NOT NULL, display_name TEXT, created_at TEXT NOT NULL, UNIQUE(channel, external_id))` в существующей `data/memory.db`.
2. `UserRepository` принимает `Connection` или `SemanticMemory` (через который шарится соединение) и работает синхронно через `asyncio.to_thread` (как в `SemanticMemory`).
3. Контракт `get_or_create / get / get_by_external` сохраняется бит-в-бит; единственное отличие — `user.id` стабилен между рестартами.
4. **Бэкап старых сессий**: добавить лог `INFO` при старте о текущем количестве пользователей в БД (sanity).
5. `UserCreated` публикуется только при реальном `INSERT` (не при чтении существующего).

#### Definition of Done

- [x] `tests/users/test_repository.py` дополнен кейсом «рестарт»: создаём пользователя, закрываем репозиторий, открываем новый поверх той же БД (`tmp_path`), `get_or_create` возвращает того же `user.id`.
- [x] `UserCreated` публикуется ровно один раз на каждого нового пользователя через все рестарты.
- [x] `_docs/memory.md` дополнен схемой `users`; `_docs/current-state.md` §1.5 обновлён.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 6. Этап 3. Удаление legacy `file_contexts.db`

После спринта 06 (`dialog_journal` — единый источник истины для file_id/file_path/content) сама БД и миграционный код больше не нужны.

### Задача 3.1. Удалить миграционный код и БД

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/current-state.md` §1.7, `_docs/memory.md` §2.6, `_board/sprints/06-reliability-and-observability.md` (Этап 3-bis).
- **Затрагиваемые файлы:** `app/services/file_contexts_migration.py` (удалить), `app/main.py` / `app/console_main.py` (убрать вызов миграции), `data/file_contexts.db` (удалить из `.gitignore` уже не нужно, файл всё равно gitignored), `_docs/current-state.md`, `_docs/memory.md`.

#### Описание

1. Убедиться, что вызов миграции в `main.py`/`console_main.py` — единственное место использования модуля.
2. Удалить `app/services/file_contexts_migration.py` и его импорт.
3. Удалить из README/документации упоминания о миграции (или пометить как «исторический шаг, выполнен в спринте 06»).
4. **Не удалять** автоматически `data/file_contexts.db` у пользователей: добавить в `_docs/current-state.md` §6 «История закрытий» инструкцию «можно безопасно удалить вручную после обновления».

#### Definition of Done

- [x] `grep -rn "file_contexts" app/ tests/` возвращает только записи о новой таблице `file_contexts` в `ConversationStore` (если ещё используется) или ничего.
- [x] `pytest -q` зелёный без падений от отсутствия миграционного модуля.
- [x] `_docs/current-state.md` §1.7 обновлён: запись о legacy переведена в §6 «История закрытий» с указанием спринта 08.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — `n/a` (удаление мёртвого кода).
- [x] `git status` чист.

## 7. Этап 4. Регрессионный тест на длительность `/new`

DoD задачи 03.1.1 «< 30 секунд на 50+ сообщений» был проверен вручную. Регрессии нет — оптимизации параллельного embedding могут регрессировать без сигнала.

### Задача 4.1. Регрессионный тест `Archiver.archive` с бюджетом

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/commands.md` § `/new`, `_docs/architecture.md` §5, `_board/sprints/03-bugs-and-console.md` Задача 1.1.
- **Затрагиваемые файлы:** `tests/services/test_archiver.py` (расширение), `app/services/archiver.py` (без правок, если уже устроен под тест).

#### Описание

1. Сгенерировать синтетическую сессию из 50 сообщений (через `ConversationStore` напрямую).
2. Запустить `Archiver.archive` с **мок-LLM** (детерминированные эмбеддинги, мгновенная суммаризация).
3. Проверить, что вызов завершается за разумный бюджет на мок-LLM (например, `< 2.0` секунд) — не «реальные 30», а **отсутствие неявных O(N²) / sleep'ов**.
4. Тест маркируется `@pytest.mark.slow` и пропускается на CI, если в `pyproject.toml` есть соответствующий маркер (или включается флагом).

#### Definition of Done

- [x] Тест проходит локально и в CI, добавлен маркер.
- [x] При искусственном замедлении (`asyncio.sleep(5)`) тест падает — sanity.
- [x] **Документация обновлена** — `_docs/testing.md` (упомянуть маркер `slow`, если ещё не описан).
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 8. Этап 5. Финальная документация

### Задача 5.1. Обновить `current-state.md` и `roadmap.md`

- **Статус:** Done
- **Приоритет:** low
- **Объём:** XS
- **Зависит от:** Задача 1.1, Задача 2.1, Задача 3.1.
- **Связанные документы:** `_docs/current-state.md`, `_docs/roadmap.md`.
- **Затрагиваемые файлы:** `_docs/current-state.md`, `_docs/roadmap.md`.

#### Описание

1. В `_docs/current-state.md` §1 добавить запись про secure-by-default allowlist и персистентный `UserRepository`.
2. В §3 (архитектурные нюансы) — пункт про smock-by-default безопасность tools.
3. В §6 (история закрытий) — две записи про спринт 08.
4. В `_docs/roadmap.md` — если есть пункт про hardening, пометить закрытым; иначе ничего не добавлять.

#### Definition of Done

- [x] Документы актуализированы.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — `n/a`.
- [x] `git status` чист.

## 9. Этап 6. Top-level логирование необработанных исключений

Закрываем системный пробел п.5 из §1: падения в `run()` теряются мимо JSON-логов и Sentry.

### Задача 6.1. Логировать необработанные исключения в обёртках `run()`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/observability.md` §1–§5, `_docs/current-state.md` §3.
- **Затрагиваемые файлы:** `app/main.py`, `app/console_main.py`, `tests/test_main.py`, `_docs/current-state.md`.

#### Описание

1. В `app/main.py::run` обернуть `asyncio.run(main())` в `try/except`:
   - `KeyboardInterrupt` — пробросить без лога (штатное завершение polling).
   - `BaseException` — `logger.exception("необработанное исключение на верхнем уровне")` + `raise`.
2. Симметрично применить к `app/console_main.py::run`.
3. Тест в `tests/test_main.py`: мокнуть `asyncio.run` так, чтобы он бросил `RuntimeError("boom")`, проверить, что `run()` повторно бросает то же исключение и в caplog есть запись уровня `ERROR` с traceback. Аналогичный тест на `app/console_main.py` (можно в том же файле).

Изменение хирургическое: только два места, без `sys.excepthook` (Sentry handler уже подхватывает `logger.exception` через `LoggingIntegration`).

#### Definition of Done

- [x] `app/main.py::run` и `app/console_main.py::run` обновлены по описанию.
- [x] `tests/test_main.py` содержит хотя бы один тест на каждую точку входа: `RuntimeError` пробрасывается, `caplog` содержит запись `ERROR` с traceback; отдельный кейс: `KeyboardInterrupt` пробрасывается без записи `ERROR`.
- [x] `pytest -q` и `flake8 app tests` зелёные.
- [x] **Документация обновлена** — `_docs/current-state.md` §3 (нюанс про top-level логирование).
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 10. Этап 7. Фикс user_id в LoggingMiddleware

Закрываем баг наблюдаемости: во всех JSON-записях `agent.log` поле `user_id` равно `null`, хотя `LoggingMiddleware` обязан биндить `user_id` в contextvars.

### Задача 7.1. Извлекать `user_id`/`chat_id` из `data` для `Update`

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/observability.md` §2, `_docs/architecture.md` §3.12.
- **Затрагиваемые файлы:** `app/middlewares/logging_mw.py`, `tests/test_middleware_logging.py`, `_docs/observability.md`.

#### Описание

`LoggingMiddleware` зарегистрирован через `dispatcher.update.middleware(...)` и получает объект `Update`, у которого нет атрибутов `from_user`/`chat` — они есть только у вложенных событий (`Message`, `CallbackQuery` и т.д.). В результате `_extract_ids` возвращает `(None, None)`, `bind_user_id(None)` — и каждая JSON-запись в `logs/agent.log` получает `"user_id": null`.

Aiogram в inner-middleware на `dispatcher.update` уже заполняет в `data` ключи `event_from_user` и `event_chat` (через встроенный `UserContextMiddleware`) до вызова нашего middleware — берём их оттуда, с фолбэком на атрибуты события.

Шаги:

1. В `_extract_ids` добавить параметр `data: dict[str, Any]`, читать `data.get("event_from_user")` / `data.get("event_chat")` в первую очередь.
2. Передать `data` в вызов `_extract_ids` из `__call__`.
3. Добавить регрессионный тест: событие без `from_user`/`chat` (например, `MagicMock(spec=[])`), `data={"event_from_user": ..., "event_chat": ...}` → `bind_user_id` получает корректный `id`, INFO-строка содержит `user=<id>`.
4. В `_docs/observability.md` §2 уточнить, откуда middleware берёт `user_id`.

#### Definition of Done

- [x] `tests/test_middleware_logging.py` содержит тест-кейс «Update без `from_user`, `data` с `event_from_user`», падающий до фикса и зелёный после.
- [x] Существующие тесты `test_middleware_logging.py` остаются зелёными.
- [x] `_docs/observability.md` §2 обновлён: явно указано, что `LoggingMiddleware` читает `event_from_user`/`event_chat` из `data`.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — да.
- [x] `git status` чист.

## 11. Этап 8. Настройка прокси для Telegram API в WSL

Закрываем проблему сетевого подключения в WSL: IPv6 DNS resolution вызывает timeout при подключении к Telegram API.

### Задача 8.1. Настроить aiogram на использование системного прокси

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/current-state.md`.
- **Затрагиваемые файлы:** `app/main.py`, `_docs/current-state.md`.

#### Описание

В WSL aiogram по умолчанию не использует переменные окружения `HTTP_PROXY`/`HTTPS_PROXY`, что приводит к timeout ошибкам при подключении к Telegram API через системный прокси.

Решение:
1. Monkey-patch `aiohttp.ClientSession.__init__` для добавления `trust_env=True` при наличии переменных окружения прокси.
2. В `_wire_telegram` прочитать прокси из переменных окружения и передать параметр `proxy` в Bot.
3. Добавить `request_timeout=30` для уменьшения таймаута.
4. Добавить graceful shutdown через сигналы SIGTERM/SIGINT для корректного завершения всех фоновых задач при принудительной остановке приложения.

Шаги:

1. Добавить импорт `aiohttp` в `app/main.py`.
2. Добавить monkey-patch для `aiohttp.ClientSession.__init__`.
3. В `_wire_telegram` прочитать прокси из переменных окружения.
4. Передать `proxy` и `request_timeout=30` в Bot.
5. Добавить обработку сигналов SIGTERM/SIGINT для graceful shutdown.
6. Обновить документацию с описанием решения.

#### Definition of Done

- [x] Monkey-patch aiohttp добавлен, proxy параметр передан в Bot (бот подключается к Telegram API через прокси).
- [x] Сервис запускается и отвечает на сообщения без timeout ошибок.
- [x] `_docs/current-state.md` обновлён с описанием решения.
- [x] **Документация обновлена** — да.
- [x] **Тесты добавлены / обновлены** — `n/a` (инфраструктурное изменение).
- [x] `git status` чист.

## 12. Этап 9. Оптимизация производительности архивации

Закрываем проблему медленного выполнения джоб: последовательная запись чанков в БД создаёт bottleneck при `/new`.

### Задача 9.1. Добавить batch insert в SemanticMemory

- **Статус:** Progress
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §3, `_docs/architecture.md` §5.
- **Затрагиваемые файлы:** `app/services/memory.py`, `tests/services/test_memory.py`.

#### Описание

Текущий `SemanticMemory.insert()` делает два SQL запроса и commit для каждого чанка отдельно. Это создаёт bottleneck при архивации сессий с большим количеством чанков.

Решение:
1. Добавить метод `insert_batch(items: list[tuple[str, list[float], dict[str, Any]]]) -> list[int]` который принимает список (text, embedding, metadata).
2. Внутри одной транзакции выполнить все INSERT в `memory_chunks` и `memory_vec`, затем один commit.
3. Сохранить существующий `insert()` для обратной совместимости (он может вызывать `insert_batch` с одним элементом).
4. Добавить тест для `insert_batch` в `tests/services/test_memory.py`.

#### Definition of Done

- [ ] Метод `insert_batch` добавлен в `SemanticMemory`, возвращает список rowid.
- [ ] Тест в `tests/services/test_memory.py` проверяет, что `insert_batch` вставляет несколько чанков в одной транзакции (проверяется через rollback при ошибке).
- [ ] Существующий `insert()` использует `insert_batch` под капотом.
- [ ] `pytest tests/services/test_memory.py -q` зелёный.
- [ ] **Документация обновлена** — `_docs/memory.md` §3 (описание API).
- [ ] **Тесты добавлены / обновлены** — да.
- [ ] `git status` чист.

### Задача 9.2. Оптимизировать Archiver для использования batch insert

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 9.1
- **Связанные документы:** `_docs/memory.md` §3.3, `_docs/architecture.md` §5.
- **Затрагиваемые файлы:** `app/services/archiver.py`, `tests/services/test_archiver.py`.

#### Описание

Текущий `Archiver.archive()` (строки 149-160) записывает чанки в БД последовательно в цикле, каждый вызов через `await`. Это узкое место.

Решение:
1. Заменить цикл на один вызов `await self._memory.insert_batch(...)`.
2. Подготовить данные: список кортежей `(chunks[idx], vector, metadata)`.
3. Обновить логирование в этом этапе (записывать количество чанков за один вызов).
4. Обновить тест `test_archive_full_flow` чтобы он проверял использование batch insert (можно через мок).

#### Definition of Done

- [ ] Цикл последовательной записи заменён на один вызов `insert_batch`.
- [ ] Логирование обновлено (одна запись для всех чанков).
- [ ] Тест `test_archive_full_flow` остаётся зелёным.
- [ ] `pytest tests/services/test_archiver.py -q` зелёный.
- [ ] **Документация обновлена** — `_docs/memory.md` §3.3 (описание потока архивации).
- [ ] **Тесты добавлены / обновлены** — да.
- [ ] `git status` чист.

### Задача 9.3. Добавить настройку EMBEDDING_CONCURRENCY в .env.example

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** —
- **Связанные документы:** `_docs/stack.md` §9, `app/config.py`.
- **Затрагиваемые файлы:** `.env.example`.

#### Описание

Настройка `embedding_concurrency` существует в `config.py` (дефолт 5), но не документирована в `.env.example`. Пользователь не знает, что может настроить параллелизм embedding.

Решение:
1. Добавить строку `EMBEDDING_CONCURRENCY=5` в `.env.example` с комментарием.
2. Добавить описание в `_docs/stack.md` §9.

#### Definition of Done

- [ ] `.env.example` содержит `EMBEDDING_CONCURRENCY=5` с поясняющим комментарием.
- [ ] `_docs/stack.md` §9 обновлён с описанием настройки.
- [ ] **Документация обновлена** — да.
- [ ] **Тесты добавлены / обновлены** — `n/a` (только документация).
- [ ] `git status` чист.

## 13. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | Смена дефолта `dangerous_tools_allowlist` сломает существующих пользователей (внезапно перестанут работать `http_request` / `read_*`). | Подсказка в логах при старте + явная запись в `_docs/current-state.md` §6; `.env.example` содержит закомментированную строку с готовой миграцией. |
| 2 | SQLite-`UserRepository` создаст гонки на `data/memory.db` (соединение шарится с `SemanticMemory`, `DialogJournal`). | Все операции через единственное соединение `SemanticMemory`, как уже сделано для `DialogJournal` в спринте 06; запись — через `asyncio.to_thread`. |
| 3 | Удаление миграционного кода `file_contexts` лишит существующих пользователей одноразовой миграции. | Проверить, что миграция уже отработала у всех известных установок (вопрос пользователю в `progress.txt`); оставить инструкцию в `_docs/current-state.md` §6. |
| 4 | Bypass-тесты обнажат слепые зоны санитайзеров — соблазн расширять паттерны бесконечно. | DoD явно разрешает зафиксировать known-limitations в `_docs/security.md` вместо немедленного «закрытия всего». |
| 5 | Регрессионный тест на `/new` будет flaky на CI из-за фоновых процессов. | Бюджет с запасом (например, 2.0s при ожидаемых 50–100ms на мок-LLM); маркер `slow`, опциональный запуск в CI. |
| 6 | `logger.exception` в `run()` может задвоить вывод (stderr + JSON-handler). | На текущей конфигурации `setup_logging` ставит один root handler; задвоения нет. Если появится — переключить уровень exception на `error` без stacktrace. |

## 12. Сводная таблица задач спринта

| #   | Задача                                                | Приоритет | Объём | Статус | Зависит от        |
|-----|-------------------------------------------------------|:---------:|:-----:|:------:|:-----------------:|
| 1.1 | Secure-by-default `dangerous_tools_allowlist`         | high      | S     | Done   | —                 |
| 1.2 | Bypass-тесты для `InputSanitizer` / `ResponseSanitizer` | high    | S     | Done   | —                 |
| 2.1 | SQLite-реализация `UserRepository` с миграцией        | high      | M     | Done   | —                 |
| 3.1 | Удалить миграционный код и legacy `file_contexts.db`  | medium    | S     | Done   | —                 |
| 4.1 | Регрессионный тест `Archiver.archive` с бюджетом      | medium    | S     | Done   | —                 |
| 5.1 | Обновить `current-state.md` и `roadmap.md`            | low       | XS    | Done   | 1.1, 2.1, 3.1, 6.1 |
| 6.1 | Логировать необработанные исключения в `run()`        | medium    | XS    | Done   | —                 |
| 7.1 | Фикс `user_id` в `LoggingMiddleware`                  | medium    | XS    | Done   | —                 |
| 8.1 | Настроить aiogram на использование системного прокси | high      | S     | Done   | —                 |
| 9.1 | Добавить batch insert в SemanticMemory                | high      | M     | Progress | —              |
| 9.2 | Оптимизировать Archiver для использования batch insert | high    | S     | ToDo   | 9.1               |
| 9.3 | Добавить настройку EMBEDDING_CONCURRENCY в .env.example | medium  | XS    | ToDo   | —                 |

> Обновляется при каждом переходе статуса и при добавлении/удалении задач.

## 13. История изменений спринта

- **2026-05-20** — файл спринта создан (статус `ToDo`, ветка ещё не открыта). Открытие — после закрытия спринта 07; см. `_board/process.md` §2 п.1.
- **2026-05-21** — спринт открыт, ветка `feature/08-hardening-and-cleanup` создана от `main`. Добавлен Этап 6 / Задача 6.1 (top-level логирование необработанных исключений) на основании рабочей правки `app/main.py` от 21.05.2026.
- **2026-05-21** — закрыта задача 08.6.1: top-level логирование необработанных исключений в `app/main.py::run` и `app/console_main.py::run` (коммиты `cb59183` docs, `8c77cd0` feat).
- **2026-05-21** — закрыта задача 08.2.1: SQLite-`UserRepository` с таблицей `users` в `data/memory.db`; `init/close` в точках входа; `UserCreated` публикуется ровно при `INSERT`; регрессия на рестарт в `tests/users/test_repository.py`; документация `_docs/current-state.md` §1.5/§3/§6.4 обновлена (коммиты `dc91f564` start, `ea229241` docs, `5b55c5fe` feat, `2a4e919a` close).
- **2026-05-21** — закрыта задача 08.3.1: удалены `app/services/file_contexts_migration.py`, `tests/services/test_file_contexts_migration.py` и вызовы в `app/main.py`/`app/console_main.py`; `_docs/memory.md` §2.6.1/§4.1, `_docs/security.md` §2, `_docs/current-state.md` §1.7/§6.5 обновлены (коммиты `1f64d3d1` start, `9fdb67af` docs, `9e582a6c` refactor, `d04c87c6` close).
- **2026-05-21** — закрыта задача 08.4.1: регрессионный `tests/services/test_archiver.py::test_archive_completes_within_budget` с бюджетом < 2.0s и маркером `slow`; маркер зарегистрирован в `pyproject.toml`, описан в `_docs/testing.md` §2 (коммиты `f2f0f674` start, `a2232069` chore, `4c4746f4` docs, `fbd66e1f` test, `e4c1e3f0` close).
- **2026-05-21** — закрыта задача 08.5.1: финальные записи в `_docs/current-state.md` (§1.5, §3, §6.4, §6.5); в `roadmap.md` правок не требуется (коммиты `8768856e` start, `8eb56bdb` close).
- **2026-05-21** — закрыта задача 08.1.1: secure-by-default для `dangerous_tools_allowlist` (WARNING при отказе, INFO-подсказка при старте, `.env.example` и `_docs/security.md` обновлены; коммиты `14855c2` docs, `27a6829` feat).
- **2026-05-21** — закрыта задача 08.1.2: bypass-тесты для `InputSanitizer`/`ResponseSanitizer` (8+8 кейсов, known-limitations зафиксированы в `_docs/security.md` §5; коммиты `fb42297` docs, `67ef911` test).
- **2026-05-21** — добавлен и закрыт Этап 7 / задача 08.7.1: фикс `user_id` в `LoggingMiddleware` (`Update` без `from_user` — берём из `data['event_from_user']`; коммиты `dbcb3b2` docs, `8910039` test, `13932c0` fix).
- **2026-05-21** — закрыта задача 08.8.1: настройка aiogram на использование системного прокси через monkey-patch aiohttp и явную передачу proxy в Bot; документация `_docs/current-state.md` §6.6 обновлена; добавлен graceful shutdown через сигналы SIGTERM/SIGINT для корректного завершения всех фоновых задач (коммиты `146bf675` start, `d66da4de` feat, `a7ecf4c1` feat).
- **2026-05-21** — спринт закрыт, все задачи выполнены (9/9 Done), ветка готова к merge в main.
- **2026-05-22** — спринт reopen для добавления задач по оптимизации производительности (запрос пользователя); добавлен Этап 9 с задачами 9.1 (batch insert), 9.2 (оптимизация Archiver), 9.3 (документация EMBEDDING_CONCURRENCY).
