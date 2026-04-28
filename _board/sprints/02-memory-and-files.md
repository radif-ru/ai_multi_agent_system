# Спринт 02. Память и файловые входы

- **Источник:** обратная связь пользователя (бот не помнит контекст между сообщениями; не принимает файлы); `_docs/roadmap.md` Этап 7 (частично); `_docs/memory.md` §2–3 (готовый, но не подключённый слой).
- **Ветка:** `feature/02-memory-and-files` (от `main`, после merge `feature/mvp-agent` → `main`).
- **Открыт:** 2026-04-29
- **Закрыт:** —

## 1. Цель спринта

Закрыть две независимо обнаруженные дыры в MVP:

1. **Память не доходит до LLM.** `ConversationStore` и `SemanticMemory` реализованы и покрыты тестами в Спринте 01, но `Executor.run` каждый раз собирает `messages = [system, user_goal]` с нуля (`@/home/radif/my/ai_multi_agent_system/app/agents/executor.py:75-78`), а долгосрочная память подключена только через tool `memory_search`, которое модель должна вызвать сама. На практике это даёт эффект «каждое сообщение — новая сессия» (см. скриншот пользователя).
2. **Бот не принимает файлы.** Telegram-handler в `@/home/radif/my/ai_multi_agent_system/app/adapters/telegram/handlers/messages.py` ловит любое сообщение, но при `message.text is None` отвечает `«В MVP я понимаю только текст»` и не умеет работать с `Photo` / `Voice` / `Document`. Документация `_docs/roadmap.md` Этап 7 предусматривала отдельный спринт; пользователь явно попросил начать сейчас.

После спринта пользователь в Telegram получает: (а) непрерывный контекст внутри сессии и видимость прошлых сессий через `/new`-архив, (б) возможность кинуть боту PDF / голосовое / фото и получить осмысленный ответ.

## 2. Скоуп и non-goals

### В скоупе

- Подключение `ConversationStore` к `Executor` (история уходит в LLM).
- Авто-подгрузка релевантных саммари из `SemanticMemory` при старте новой сессии.
- Обработчики Telegram для `Photo`, `Voice`, `Document`, маршрутизация в агентный цикл.
- Tool(ы) для извлечения текста из документов (PDF, plain-text, markdown).
- Лимит размера принимаемого файла (`TELEGRAM_MAX_FILE_MB`).
- Обновление `_docs/agent-loop.md`, `_docs/memory.md`, `_docs/architecture.md`, `_docs/commands.md`, `_docs/tools.md`, `_docs/requirements.md`, `_docs/current-state.md`, `README.md`, `_board/progress.txt`.

### Вне скоупа

- Multi-agent (Planner/Critic) — Этап 4 roadmap.
- Streaming шагов — Этап 2 roadmap.
- Стриминг ответа Ollama — Этап 3 roadmap.
- Webhook — Этап 6.
- Throttling — Этап 9.
- Видео, стикеры, location, polls — пока не нужны.
- Vision-модель в Ollama: подключение конкретной vision-модели остаётся опциональным; если модель недоступна — handler `Photo` отвечает осмысленным fallback'ом, но не падает.

## 3. Acceptance Criteria спринта

- [ ] В переписке `Привет, я Радиф / Как меня зовут?` бот отвечает корректным именем, не теряет контекст между ходами.
- [ ] После `/new` и нового вопроса по теме прошлой сессии бот **сам** подмешивает релевантные чанки из `data/memory.db` (через авто-подгрузку или явный вызов `memory_search`) — проверяется тестом и smoke-проверкой.
- [ ] При `/new` в долгосрочную память уходит **вся** история сессии, а не усечённая `replace_with_summary` верхушка: имя/факты, упомянутые в начале длинной сессии, доступны через `memory_search` / авто-подгрузку после `/new` (регрессионный тест).
- [ ] Бот принимает PDF/TXT/MD как `Document` и отвечает по содержимому.
- [ ] Бот принимает голосовое (`Voice`) и распознаёт речь в текст, текст уходит в агентный цикл.
- [ ] Бот принимает фото (`Photo`) и либо распознаёт через vision-модель, либо отвечает понятным сообщением «vision-модель не настроена», без падения.
- [ ] Превышение `TELEGRAM_MAX_FILE_MB` → понятное сообщение пользователю, файл не скачивается.
- [ ] `pytest -q` зелёный, новые компоненты покрыты unit-тестами.
- [ ] `_docs/agent-loop.md`, `_docs/memory.md`, `_docs/architecture.md`, `_docs/commands.md`, `_docs/tools.md`, `_docs/requirements.md`, `README.md` соответствуют коду.
- [ ] `_board/progress.txt` дополнен чек-листом приёмки Спринта 02.
- [ ] Все задачи спринта — `Done`.

## 4. Этап 1. Краткосрочная память: история в LLM

Цель — устранить корневую причину «новая сессия на каждое сообщение».

### Задача 1.1. Спецификация склейки истории

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/agent-loop.md` §4, `_docs/memory.md` §2, `_docs/architecture.md` §3.5, §3.10, §3.11.
- **Затрагиваемые файлы:** `_docs/agent-loop.md`, `_docs/memory.md`, `_docs/architecture.md`.

#### Описание

Зафиксировать в документации, как именно `ConversationStore` подключается к LLM-вызову:

- `Executor.run` принимает `history: list[dict]` и собирает `messages = [system] + history + [user: goal]` (если `goal` уже последний user-message в `history`, он не дублируется; см. ниже задачу 1.3 о порядке).
- Внутрицикловые `assistant`/`Observation` пары не пишутся в `ConversationStore` — только финальный ответ.
- Привести обновлённый псевдокод в `agent-loop.md` §4.
- В `memory.md` добавить секцию «§2.4 Подгрузка истории в LLM» с диаграммой.

#### Definition of Done

- [x] `agent-loop.md` §4 — псевдокод соответствует целевой реализации задачи 1.2.
- [x] `memory.md` §2.4 — описан порядок добавления user-сообщения и склейки.
- [x] `architecture.md` §3.10 / §3.11 — упоминание `history` в контракте `Executor.run` / `core.handle_user_task`.
- [x] Тесты: n/a (документация).
- [x] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.2. `Executor.run` принимает `history`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/agent-loop.md` §4; `_docs/testing.md` §3.4.
- **Затрагиваемые файлы:** `app/agents/executor.py`, `tests/agents/test_executor.py`.

#### Описание

Добавить параметр `history: list[dict[str, str]] | None = None` в `Executor.run`. Склейка: `[system] + (history or []) + [user: goal]`, где `goal` дублируется только если в конце `history` его нет (страховка от двойного добавления). Сигнатура и логи остаются обратно-совместимыми (если `history=None` — поведение Спринта 01).

#### Definition of Done

- [x] Сигнатура `Executor.run` обновлена; вызовы внутри `core` — будут обновлены в задаче 1.3 (параметр опциональный, совместимость сохранена).
- [x] Тест `test_executor_uses_history` — проверяет, что `messages`, переданные в `llm.chat`, содержат `system` + историю + `user goal` в правильном порядке.
- [x] Тест `test_executor_history_none_back_compat` — старый сценарий без истории работает.
- [x] `pytest -q` зелёный.

---

### Задача 1.3. `core.handle_user_task` пробрасывает историю

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.2
- **Связанные документы:** `_docs/architecture.md` §3.10; `_docs/agent-loop.md` §4.
- **Затрагиваемые файлы:** `app/core/orchestrator.py`, `tests/core/test_orchestrator.py`.

#### Описание

`handle_user_task` достаёт `history = conversations.get_history(user_id)` и передаёт в `Executor.run`. Поскольку адаптер уже вызывает `add_user_message(user_id, text)` **до** `handle_user_task` (`@/home/radif/my/ai_multi_agent_system/app/adapters/telegram/handlers/messages.py:79`), последний элемент `history` — это и есть текущий `goal`. Принимаем такой инвариант: `goal` берётся из `text`, в `messages` подаётся `history` целиком, дубликат не делаем.

#### Definition of Done

- [x] `core.handle_user_task` достаёт историю и передаёт в executor.
- [x] Тест `test_orchestrator_passes_history` — мок `Executor`, проверка получения истории.
- [x] Тест `test_orchestrator_does_not_duplicate_goal` — последний user-message в `history` совпадает с `text`, дедупликация выполняется в `Executor.run` (задача 1.2).
- [x] `pytest -q` зелёный.

---

### Задача 1.4. Регрессионный тест диалога

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 1.3
- **Связанные документы:** `_docs/testing.md` §3.4, §3.11.
- **Затрагиваемые файлы:** `tests/test_dialog_memory.py` (новый).

#### Описание

End-to-end тест с моком LLM: имитировать три обмена «Привет, я Радиф / Как меня зовут / Что я говорил?», проверить, что 3-й вызов `llm.chat` получает в `messages` обе предыдущие пары.

#### Definition of Done

- [x] Тест зелёный, без сетевых вызовов.
- [x] `pytest -q` зелёный.

---

## 5. Этап 2. Долгосрочная память: авто-подгрузка архива

Цель — сделать `/new`-архив реально полезным: при старте новой сессии релевантные чанки прошлых сессий должны попадать в контекст автоматически.

### Задача 2.1. Спецификация авто-подгрузки

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/memory.md` §3, §5; `_docs/architecture.md` §3.10.
- **Затрагиваемые файлы:** `_docs/memory.md`, `_docs/architecture.md`, `_docs/stack.md`, `.env.example`.

#### Описание

Зафиксировать дизайн: при первом сообщении новой сессии (в `core.handle_user_task`, если `len(history) == 1`) делается embed запроса → `SemanticMemory.search(top_k=SESSION_BOOTSTRAP_TOP_K, scope_user_id=user_id)`; найденные чанки склеиваются в один `system`-message `«Контекст из прошлых сессий: …»` и подмешиваются в начало истории (после основного system-prompt). Контролируется флагом `SESSION_BOOTSTRAP_ENABLED` и параметром `SESSION_BOOTSTRAP_TOP_K`.

Альтернатива (если решим иначе по обсуждению с пользователем): не подгружать автоматически, а только усилить инструкцию в `_prompts/agent_system.md` и положиться на tool `memory_search`. Решение фиксируется здесь.

#### Definition of Done

- [x] `_docs/memory.md` — новый раздел «§3.6 Авто-подгрузка архива в новую сессию».
- [x] `_docs/stack.md` §9 — добавлены `SESSION_BOOTSTRAP_ENABLED`, `SESSION_BOOTSTRAP_TOP_K`.
- [x] `.env.example` — новые параметры.
- [x] Тесты: n/a (документация).

---

### Задача 2.2. Реализация авто-подгрузки + тесты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.3, Задача 2.1
- **Связанные документы:** `_docs/memory.md` §3.6 (новый); `_docs/testing.md` §3.7.
- **Затрагиваемые файлы:** `app/core/orchestrator.py` (или новый `app/services/session_bootstrap.py`), `app/config.py`, `tests/core/test_orchestrator.py`, `tests/services/test_session_bootstrap.py`.

#### Описание

Реализовать модуль `SessionBootstrap` (или функцию в `orchestrator`), который при первом сообщении новой сессии делает embed + `search` + форматирование `system`-message. Падение `SemanticMemory` или `embed` — `WARNING`, основной ход не страдает (сессия стартует без авто-контекста).

#### Definition of Done

- [x] Реализация по спецификации задачи 2.1.
- [x] `Settings`-валидаторы для новых полей.
- [x] Тесты: успешная подгрузка; пустой архив (graceful no-op); падение embed/search → `WARNING`, ход продолжается; флаг `SESSION_BOOTSTRAP_ENABLED=false` отключает поведение.
- [x] `pytest -q` зелёный.

---

## 6. Этап 3. Файловые входы

Цель — принимать `Photo` / `Voice` / `Document` и подключать их в агентный цикл. Все файлы скачиваются во временный путь, удаляются после обработки.

### Задача 3.1. Утилита загрузки файла из Telegram + лимиты

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md`, `_docs/stack.md` §9, `_docs/requirements.md`.
- **Затрагиваемые файлы:** `app/adapters/telegram/files.py` (новый), `app/config.py`, `.env.example`, `tests/adapters/telegram/test_files.py` (новый).

#### Описание

Async-утилита `download_telegram_file(bot, file_id, *, max_size_mb) -> Path`. Проверяет `file_size` до скачивания, кидает `FileTooLarge` (новое исключение) при превышении. Скачивает в `tempfile.NamedTemporaryFile` с auto-cleanup-контекст-менеджером.

#### Definition of Done

- [x] Утилита реализована, лимит конфигурируется через `TELEGRAM_MAX_FILE_MB`.
- [x] Тесты: успех, превышение лимита, ошибка скачивания.
- [x] `pytest -q` зелёный.

---

### Задача 3.2. Tool `read_document` (PDF/TXT/MD)

- **Статус:** Progress
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/tools.md`, `_docs/testing.md` §3.5.
- **Затрагиваемые файлы:** `app/tools/read_document.py` (новый), `app/main.py` (регистрация), `tests/tools/test_read_document.py` (новый), `requirements.txt` (`pypdf`).

#### Описание

Tool `read_document(path: str, max_chars: int = 8000) -> str`: определяет тип по расширению, извлекает текст (PDF — через `pypdf`, TXT/MD — `Path.read_text`), усекает до `max_chars`. Не читает произвольные пути из ФС — принимает только пути под каталогом `Settings.tmp_files_dir` (защита от path traversal, аналогично `read_file`).

#### Definition of Done

- [ ] Tool реализован и зарегистрирован.
- [ ] Тесты: PDF, TXT, неизвестное расширение → `ToolError`, превышение `max_chars` → усечение, попытка выхода за `tmp_files_dir` → `ToolError`.
- [ ] `pytest -q` зелёный.

---

### Задача 3.3. Handler `Document`

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 3.1, Задача 3.2
- **Связанные документы:** `_docs/commands.md`, `_docs/architecture.md` §4.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py` (расширение или новый `documents.py`), `tests/adapters/telegram/test_documents.py` (новый).

#### Описание

Принять `Document`, скачать (задача 3.1), положить путь во временную папку, передать в `core.handle_user_task` обогащённый `goal` вида: `«Пользователь прислал документ {path}. Caption: {caption}. Прочитай через read_document и ответь по сути.»` либо через предзагрузку в `system`-message. Точный формат фиксируется в задаче 3.1 (или отдельным мини-обсуждением).

#### Definition of Done

- [ ] Handler реализован, регистрируется в `messages_router`.
- [ ] Тест: получение `Document`, проверка вызова `core.handle_user_task` с обогащённым текстом.
- [ ] Тест: превышение `TELEGRAM_MAX_FILE_MB` → понятное сообщение, executor не вызывается.
- [ ] `pytest -q` зелёный.

---

### Задача 3.4. Handler `Voice` / `Audio` (распознавание речи)

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** L
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/roadmap.md` Этап 7; `_docs/stack.md`.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `app/services/transcribe.py` (новый), `requirements.txt` (`faster-whisper` или альтернатива), `tests/adapters/telegram/test_voice.py`, `tests/services/test_transcribe.py`.

#### Описание

`Transcriber` — обёртка над `faster-whisper` (CPU, локально); конкретная модель и язык настраиваются через `WHISPER_MODEL`, `WHISPER_LANGUAGE`. Handler `Voice`: скачать .ogg/.opus → `Transcriber.transcribe(path) -> str` → передать как обычный `text` в `core.handle_user_task`. Если `faster-whisper` не установлен (опциональная зависимость) — handler отвечает понятным сообщением, не падает.

#### Definition of Done

- [ ] `Transcriber` реализован; в тестах используется мок (без скачивания моделей).
- [ ] Handler `Voice` реализован и зарегистрирован.
- [ ] Тест: успешная транскрипция → `core.handle_user_task` вызывается с распознанным текстом.
- [ ] Тест: `Transcriber` недоступен → понятное сообщение пользователю.
- [ ] `pytest -q` зелёный.

---

### Задача 3.5. Handler `Photo` (vision)

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** M
- **Зависит от:** Задача 3.1
- **Связанные документы:** `_docs/roadmap.md` Этап 7; `_docs/stack.md` §9.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/messages.py`, `app/services/vision.py` (новый), `tests/adapters/telegram/test_photo.py`, `tests/services/test_vision.py`.

#### Описание

`Vision` — обёртка над `OllamaClient.chat` с поддержкой `images=[base64...]` (Ollama API параметр `images`). Если `VISION_MODEL` не задан или модель не доступна — handler отвечает: «Vision-модель не подключена, отправь текстом, что на картинке». Caption (если есть) пробрасывается как часть `goal`.

#### Definition of Done

- [ ] `Vision.describe(path) -> str` реализован, использует `OllamaClient`.
- [ ] Handler `Photo` реализован и зарегистрирован.
- [ ] Тест: успешное описание (с моком LLM) → текст уходит в агентный цикл.
- [ ] Тест: `VISION_MODEL` пуст → fallback-сообщение.
- [ ] `pytest -q` зелёный.

---

### Задача 3.6. Полировка: документация и чек-лист

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** все задачи Этапов 1–4
- **Связанные документы:** `_docs/architecture.md`, `_docs/commands.md`, `_docs/requirements.md`, `_docs/current-state.md`, `_docs/roadmap.md`, `README.md`, `_board/progress.txt`.
- **Затрагиваемые файлы:** перечисленные документы.

#### Описание

Свести изменения в обзорную форму: `architecture.md` (новый поток с файлами), `commands.md` (раздел «Файлы»), `requirements.md` (FR на медиа), `current-state.md` (актуальное состояние), `roadmap.md` (Этап 7 помечен как частично закрытый Спринтом 02), `README.md` (раздел «Возможности»). В `_board/progress.txt` — чек-лист приёмки Спринта 02.

#### Definition of Done

- [ ] Все перечисленные документы обновлены.
- [ ] Чек-лист в `progress.txt` заполнен.
- [ ] Тесты: n/a (документация).

---

## 7. Этап 4. Полное архивирование истории при `/new`

Цель — устранить корневую причину провала памяти: при `/new` суммаризации и архивации подвергается **вся** история сессии, а не усечённый буфер `ConversationStore` (после `replace_with_summary` от него остаются лишь summary + последние 2 сообщения).

Корневая причина (диагноз пользователя подтверждён): `messages.py` после каждого ответа при `len(history) >= history_summary_threshold` вызывает `conversations.replace_with_summary(user_id, summary, kept_tail=2)` (`@/home/radif/my/ai_multi_agent_system/app/adapters/telegram/handlers/messages.py:113-127`). После этого `cmd_new` передаёт в `Archiver` уже усечённый `get_history()` (`@/home/radif/my/ai_multi_agent_system/app/adapters/telegram/handlers/commands.py:140-152`) — ранние реплики (например, «Привет, я Радиф») в долгосрочную память не попадают.

### Задача 4.1. Диагноз и спецификация полного лога сессии

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/memory.md` §2, §3.3; `_docs/architecture.md` §3.5; `_docs/agent-loop.md` §4; `_docs/current-state.md`.
- **Затрагиваемые файлы:** `_docs/memory.md`, `_docs/architecture.md`, `_docs/current-state.md`.

#### Описание

Зафиксировать в документации диагноз и дизайн исправления: ввести в `ConversationStore` параллельный «полный лог сессии» (`session_log`) — append-only буфер всех `user`/`assistant` сообщений текущей сессии, не подверженный in-session compaction (`replace_with_summary` его не трогает). Контракт API:

- `add_user_message`, `add_assistant_message` пишут одновременно в `_messages` (как сейчас) и в `_session_log`.
- `replace_with_summary` — оставляет `_session_log` нетронутым.
- `get_session_log(user_id) -> list[Message]` — копия полного лога, для архивации.
- `clear(user_id)` и `rotate_conversation_id(user_id)` — обнуляют `_session_log` пользователя (новая сессия начинается с пустого лога).
- Верхняя страховка `SESSION_LOG_MAX_MESSAGES` (default 1000): при переполнении — отбросить голову лога c `WARNING`.

Инвариант: in-session compaction оптимизирует только контекст для LLM; долгосрочная память при `/new` всегда видит сессию целиком.

#### Definition of Done

- [x] `_docs/memory.md` — новая секция «§2.5 Полный лог сессии» с описанием буфера и инвариантов.
- [x] `_docs/memory.md` §3.3 — обновлено: `Archiver` принимает полный лог, а не in-session историю.
- [x] `_docs/architecture.md` §3.5 — упомянут новый буфер `session_log`.
- [x] `_docs/current-state.md` §2 — запись о ранее существовавшем баге (потеря ранней истории при `/new`).
- [x] Тесты: n/a (документация).

---

### Задача 4.2. `ConversationStore`: полный лог сессии

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 4.1
- **Связанные документы:** `_docs/memory.md` §2.5 (новая); `_docs/stack.md` §9.
- **Затрагиваемые файлы:** `app/services/conversation.py`, `app/config.py`, `.env.example`, `tests/services/test_conversation_store.py`.

#### Описание

Реализовать буфер `_session_log` по спецификации задачи 4.1. Добавить параметр `Settings.session_log_max_messages` (env `SESSION_LOG_MAX_MESSAGES`, default 1000) с валидатором `> 0`. `ConversationStore.__init__` принимает `session_log_max_messages: int`.

#### Definition of Done

- [x] `add_user_message` / `add_assistant_message` дублируют запись в `_session_log`.
- [x] `replace_with_summary` не модифицирует `_session_log` (тест).
- [x] `get_session_log(user_id)` возвращает независимую копию (тест на изоляцию мутаций).
- [x] `clear(user_id)` и `rotate_conversation_id(user_id)` обнуляют `_session_log` (тест).
- [x] Переполнение `SESSION_LOG_MAX_MESSAGES` → отбрасывание головы + одно `WARNING` (тест).
- [x] `Settings` — поле и валидатор; `.env.example` обновлён.
- [x] `pytest -q` зелёный.

---

### Задача 4.3. `cmd_new`: архивировать полный лог сессии

- **Статус:** Done
- **Приоритет:** high
- **Объём:** XS
- **Зависит от:** Задача 4.2
- **Связанные документы:** `_docs/commands.md` (`/new`); `_docs/memory.md` §3.3.
- **Затрагиваемые файлы:** `app/adapters/telegram/handlers/commands.py`, `tests/adapters/telegram/test_commands.py`.

#### Описание

`cmd_new` достаёт `conversations.get_session_log(user_id)` (вместо `get_history`) и передаёт его в `Archiver.archive`. Если лог пуст — поведение прежнее («Сессия пустая, новая открыта»). После успешной архивации `clear(user_id)` сбрасывает оба буфера и ротирует `conversation_id`.

#### Definition of Done

- [x] `cmd_new` использует полный лог.
- [x] Тест: после длинной сессии (≥ `history_summary_threshold` сообщений, in-session compaction сработал) `Archiver.archive` получает **полный** список без усечения.
- [x] Тест: пустой лог → старое поведение (без вызова `Archiver`).
- [x] Документ `_docs/commands.md` — секция `/new` уточнена (архивируется полный лог сессии).
- [x] `pytest -q` зелёный.

---

### Задача 4.4. Map-reduce суммаризация длинного лога

- **Статус:** Done
- **Приоритет:** medium
- **Объём:** M
- **Зависит от:** Задача 4.3
- **Связанные документы:** `_docs/memory.md` §3.3; `_prompts/summarizer.md`; `_docs/stack.md` §9.
- **Затрагиваемые файлы:** `app/services/summarizer.py`, `app/services/archiver.py`, `app/config.py`, `_prompts/summarizer.md`, `.env.example`, `tests/services/test_summarizer.py`, `tests/services/test_archiver.py`.

#### Описание

Чтобы суммаризатор не терял факты на длинном логе и не упирался в контекст модели, ввести map-reduce режим:

1. Если число сообщений > `SUMMARIZER_CHUNK_MESSAGES` (default 30) — разбить лог на батчи по сообщениям и суммаризовать каждый отдельно (map). Затем склеить мини-саммари и попросить модель свести их в финальное (reduce).
2. Короткие логи идут прежним одним проходом (back-compat).
3. Системный промпт `_prompts/summarizer.md` усилить требованием явно сохранять конкретику о пользователе: имена, даты, числа, договорённости, идентификаторы. Этот же промпт использовать и в map-, и в reduce-фазе.

#### Definition of Done

- [x] `Summarizer.summarize` поддерживает map-reduce; пороговое значение конфигурируется через `Settings.summarizer_chunk_messages`.
- [x] `_prompts/summarizer.md` обновлён, явно требует сохранять факты о пользователе.
- [x] Тесты: короткий лог → один вызов `llm.chat`; длинный лог → `ceil(N / chunk) + 1` вызовов; падение одного map-батча → `LLMError` пробрасывается (откат в `Archiver` уже покрыт в `tests/services/test_archiver.py`).
- [x] `.env.example` обновлён.
- [x] `pytest -q` зелёный.

---

### Задача 4.5. Регрессионный e2e: имя переживает `/new`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 4.3, Задача 2.2
- **Связанные документы:** `_docs/testing.md` §3.7, §3.11.
- **Затрагиваемые файлы:** `tests/test_session_archive_roundtrip.py` (новый).

#### Описание

End-to-end тест с моками `OllamaClient.chat` / `embed` и реальным/мок `SemanticMemory`: эмулировать длинный диалог (с ранней репликой «Привет, я Радиф»), достигший `history_summary_threshold` (с in-session `replace_with_summary`), затем `/new`. Проверить:

- `Archiver.archive` получает полный лог, включая раннюю реплику с именем.
- В `SemanticMemory` записан как минимум один чанк, содержащий подстроку «Радиф».
- В новой сессии `SessionBootstrap` находит этот чанк и подмешивает его в начальный `system`-message.

#### Definition of Done

- [x] Тест зелёный, без сетевых вызовов.
- [x] `pytest -q` зелёный.

---

## 8. Этап 5. Устойчивость парсера ответа модели

Цель — перестать выдавать пользователю «Модель ответила в неожиданном формате» в типовых случаях, когда модель возвращает корректный JSON, но обёрнутый в markdown-fence или с лишними пробелами. Диагноз по логам и отчёту пользователя зафиксирован в `_docs/current-state.md` §2.2.

### Задача 5.1. Снятие markdown-fence в `parse_agent_response`

- **Статус:** Done
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/agent-loop.md` §2; `_docs/current-state.md` §2.2; `_prompts/agent_system.md`.
- **Затрагиваемые файлы:** `app/agents/protocol.py`, `tests/agents/test_protocol.py`, `_prompts/agent_system.md`, `_docs/agent-loop.md`, `_docs/current-state.md`.

#### Описание

Наблюдаемая проблема (скриншот + `logs/agent.log`): `qwen3.5:4b` регулярно возвращает ответ вида:

```
```json
{ "final_answer": "Привет! Чем могу помочь?" }```
```

`parse_agent_response` (`@/home/radif/my/ai_multi_agent_system/app/agents/protocol.py:42`) делает чистый `json.loads(text)` и падает → `LLMBadResponse` → пользователю уходит `LLM_BAD_RESPONSE_REPLY` («Модель ответила в неожиданном формате»).

Решение — минимальный фикс вверху реки:

1. В `parse_agent_response` перед `json.loads` снимать обрамляющие markdown-fence: явный префикс ` ```json ` или ` ``` `, и закрывающий ` ``` `; триммить пробельные символы. Реализовать отдельной чистой функцией (например `_strip_code_fence(text) -> str`), чтобы было легко покрыть тестами.
2. **Не** пытаться выжимать JSON из произвольного prose-ответа (регекс-выдёргивания «первый `{...}`»). Обрабатываем только типовые fence-обёртки — их выдаёт модель по своей привычке.
3. Дополнительно в `_prompts/agent_system.md` явно ужесточить: в ответе — **голый JSON-объект**, без обёртки в код-блоки и каких бы то ни было комментариев.
4. Обновить `_docs/agent-loop.md` §2: зафиксировать, что парсер толерантен к fence-обёртке.
5. После исправления в `_docs/current-state.md` §2.2 перенести запись в §6 с SHA коммита.

#### Definition of Done

- [x] `parse_agent_response` корректно парсит ответ вида ` ```json\n{...}\n``` `, ` ```\n{...}\n``` ` и вариант с обрамляющими пробелами.
- [x] Бэк-компат: голый JSON-ответ парсится как раньше.
- [x] Невалидный внутри fence JSON → по-прежнему `LLMBadResponse` с осмысленным сообщением.
- [x] `_prompts/agent_system.md` явно запрещает markdown-код-блоки в ответе.
- [x] `_docs/agent-loop.md` §2 обновлён.
- [x] `_docs/current-state.md` §2.2 перенесён в §6 с SHA.
- [x] Тесты в `tests/agents/test_protocol.py` покрывают оба fence-варианта и back-compat.
- [x] `pytest -q` зелёный.

---

## 9. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | `qwen3.5:4b` плохо тянет длинный контекст из истории + авто-подгруженного архива | Жёсткие лимиты: `HISTORY_MAX_MESSAGES`, `MEMORY_SEARCH_TOP_K`, `MAX_TOOL_OUTPUT_CHARS`. При желании — переключение на модель с большим контекстом через `.env`. |
| 2 | `faster-whisper` тяжёлая зависимость (200+ MB моделей) | Делаем опциональной (`pip install` руками); при отсутствии — handler `Voice` отвечает понятным сообщением. |
| 3 | Vision-модель локально неустановлена | Аналогично: `VISION_MODEL` пуст → fallback. Тесты не требуют реальной модели. |
| 4 | PDF с защитой / сканом (без текстового слоя) | `pypdf` извлечёт пустую строку; tool возвращает `ToolError("PDF не содержит текстового слоя")`. OCR — вне скоупа. |
| 5 | Большие файлы → таймаут / переполнение памяти | `TELEGRAM_MAX_FILE_MB` (default 20). Проверка до скачивания. |
| 6 | Авто-подгрузка архива не относится к новому запросу (false positive) | Подмешиваем как `system`-сообщение, не как user-факт; модель в промпте инструктируется «использовать только если релевантно». В крайнем случае — флаг `SESSION_BOOTSTRAP_ENABLED=false`. |
| 7 | Исторические тесты сломаются от новых параметров `Executor.run` | Сделать `history` опциональным с `None` по умолчанию; обновить только тесты, явно проверяющие новое поведение. |

## 10. Сводная таблица задач спринта

| #   | Задача                                              | Приоритет | Объём | Статус | Зависит от                  |
|-----|------------------------------------------------------|:---------:|:-----:|:------:|------------------------------|
| 1.1 | Спецификация склейки истории                         | high      | S     | Done   | —                            |
| 1.2 | `Executor.run` принимает `history`                   | high      | S     | Done   | 1.1                          |
| 1.3 | `core.handle_user_task` пробрасывает историю         | high      | S     | Done   | 1.2                          |
| 1.4 | Регрессионный тест диалога                           | medium    | XS    | Done   | 1.3                          |
| 2.1 | Спецификация авто-подгрузки архива                   | high      | S     | Done   | 1.1                          |
| 2.2 | Реализация авто-подгрузки + тесты                    | high      | M     | Done   | 1.3, 2.1                     |
| 3.1 | Загрузка файла из Telegram + лимиты                  | high      | S     | Done   | —                            |
| 3.2 | Tool `read_document` (PDF/TXT/MD)                    | high      | M     | Progress | 3.1                          |
| 3.3 | Handler `Document`                                   | high      | S     | ToDo   | 3.1, 3.2                     |
| 3.4 | Handler `Voice` (faster-whisper)                     | high      | L     | ToDo   | 3.1                          |
| 3.5 | Handler `Photo` (vision)                             | medium    | M     | ToDo   | 3.1                          |
| 3.6 | Полировка: документация и чек-лист                   | high      | S     | ToDo   | все задачи Этапов 1–4        |
| 4.1 | Диагноз и спецификация полного лога сессии           | high      | S     | Done   | —                            |
| 4.2 | `ConversationStore`: полный лог сессии               | high      | S     | Done   | 4.1                          |
| 4.3 | `cmd_new`: архивировать полный лог сессии            | high      | XS    | Done   | 4.2                          |
| 4.4 | Map-reduce суммаризация длинного лога                | medium    | M     | Done   | 4.3                          |
| 4.5 | Регрессионный e2e: имя переживает `/new`             | high      | S     | Done   | 4.3, 2.2                     |
| 5.1 | Снятие markdown-fence в `parse_agent_response`         | high      | S     | Done   | —                            |

> Обновлять при каждом переходе статуса.

## 11. История изменений спринта

- **2026-04-29** — спринт открыт, ветка `feature/02-memory-and-files` создана от `main` (после merge `feature/mvp-agent` → `main` через PR #1, коммит `4011eed`).
- **2026-04-29** — закрыта задача 1.1: зафиксирована спецификация склейки истории в `_docs/agent-loop.md` §4, `_docs/memory.md` §2.4, `_docs/architecture.md` §3.10–§3.11.
- **2026-04-29** — закрыта задача 1.4: добавлен регрессионный e2e-тест `tests/test_dialog_memory.py` — проверяет, что во время трёхходового диалога история доходит до LLM. Этап 1 спринта 02 закрыт.
- **2026-04-29** — закрыта задача 1.3: `core.handle_user_task` достаёт `history` из `ConversationStore` и пробрасывает в `Executor.run`.
- **2026-04-29** — закрыта задача 1.2: `Executor.run` принимает опциональный `history` и склеивает его с системным промптом и `goal` без дублей.
- **2026-04-29** — закрыта задача 2.1: зафиксирована спецификация авто-подгрузки архива в `_docs/memory.md` §3.6, `_docs/stack.md` §9, `_docs/architecture.md` §3.10, `.env.example`.
- **2026-04-29** — закрыта задача 2.2: реализован модуль `app/services/session_bootstrap.py`, `core.handle_user_task` при `len(history) == 1` дописывает system-сообщение с результатами `SemanticMemory.search`. Этап 2 спринта 02 закрыт.
- **2026-04-29** — добавлен Этап 5 (задача 5.1) по отчёту пользователя: бот иногда отвечает «Модель ответила в неожиданном формате». Диагноз по `logs/agent.log`: `qwen3.5:4b` возвращает JSON, обёрнутый в markdown-fence (` \`\`\`json ... \`\`\` `), а `parse_agent_response` это не снимает. Баг зафиксирован в `_docs/current-state.md` §2.2.
- **2026-04-29** — закрыта задача 4.5: добавлен e2e-тест `tests/test_session_archive_roundtrip.py` — подтверждает, что имя «Радиф» из ранней реплики переживает in-session compaction, попадает в архив через `/new` и подтягивается `SessionBootstrap` в новой сессии. Этап 4 спринта 02 закрыт — корневой баг из `_docs/current-state.md` §2.1 устранён.
- **2026-04-29** — закрыта задача 4.4: `Summarizer` поддерживает map-reduce при `len(messages) > SUMMARIZER_CHUNK_MESSAGES` (default 30); короткие логи — прежним одним проходом. Добавлен `Settings.summarizer_chunk_messages` с валидатором. Промпт `_prompts/summarizer.md` усилён требованием сохранять конкретику о пользователе.
- **2026-04-29** — закрыта задача 4.3: `cmd_new` читает `ConversationStore.get_session_log()` вместо `get_history()` — корневой баг (`current-state.md` §2.1) исправлен. Регрессия покрыта `test_new_archives_full_session_log_after_in_session_compaction`. Обновлён `_docs/commands.md` §`/new`.
- **2026-04-29** — закрыта задача 4.2: `ConversationStore` ведёт параллельный append-only `_session_log`; `replace_with_summary` его не трогает; `clear` / `rotate_conversation_id` обнуляют. Добавлен `Settings.session_log_max_messages` (env `SESSION_LOG_MAX_MESSAGES`, default 1000) с валидатором.
- **2026-04-29** — закрыта задача 4.1: зафиксированы диагноз и спецификация полного лога сессии в `_docs/memory.md` §2.5, §3.3, `_docs/architecture.md` §3.5, `_docs/current-state.md` §2.1.
- **2026-04-29** — добавлен Этап 4 (задачи 4.1–4.5) по обратной связи пользователя: при `/new` в долгосрочную память уходила только усечённая `replace_with_summary` верхушка истории, из-за чего ранние факты (например, имя пользователя) терялись. Цель этапа — архивировать полный лог сессии.
- **2026-04-29** — закрыта задача 5.1: добавлена функция `_strip_code_fence` в `app/agents/protocol.py`, парсер теперь толерантен к markdown-fence обёртке (```json ... ```). В `_prompts/agent_system.md` ужесточено требование о голом JSON без обёртки. В `_docs/agent-loop.md` §2.3 зафиксирована толерантность парсера. Запись из `_docs/current-state.md` §2.2 перенесена в §6 с SHA коммита 0eacb6b. Этап 5 спринта 02 закрыт.
- **2026-04-29** — закрыта задача 3.1: добавлена утилита `download_telegram_file` в `app/adapters/telegram/files.py` с проверкой размера файла и исключением `FileTooLargeError`. Добавлен параметр конфигурации `TELEGRAM_MAX_FILE_MB` (default 20) с валидатором. Покрыто тестами: успех, превышение лимита, ошибка скачивания, отсутствие информации о размере.
