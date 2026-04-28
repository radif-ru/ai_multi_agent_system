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

- **Статус:** ToDo
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

- [ ] `agent-loop.md` §4 — псевдокод соответствует целевой реализации задачи 1.2.
- [ ] `memory.md` §2.4 — описан порядок добавления user-сообщения и склейки.
- [ ] `architecture.md` §3.10 / §3.11 — упоминание `history` в контракте `Executor.run` / `core.handle_user_task`.
- [ ] Тесты: n/a (документация).
- [ ] `git status` чист, `pytest -q` зелёный.

---

### Задача 1.2. `Executor.run` принимает `history`

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/agent-loop.md` §4; `_docs/testing.md` §3.4.
- **Затрагиваемые файлы:** `app/agents/executor.py`, `tests/agents/test_executor.py`.

#### Описание

Добавить параметр `history: list[dict[str, str]] | None = None` в `Executor.run`. Склейка: `[system] + (history or []) + [user: goal]`, где `goal` дублируется только если в конце `history` его нет (страховка от двойного добавления). Сигнатура и логи остаются обратно-совместимыми (если `history=None` — поведение Спринта 01).

#### Definition of Done

- [ ] Сигнатура `Executor.run` обновлена; вызовы внутри `core` — обновлены.
- [ ] Тест `test_executor_uses_history` — проверяет, что `messages`, переданные в `llm.chat`, содержат `system` + историю + `user goal` в правильном порядке.
- [ ] Тест `test_executor_history_none_back_compat` — старый сценарий без истории работает.
- [ ] `pytest -q` зелёный.

---

### Задача 1.3. `core.handle_user_task` пробрасывает историю

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.2
- **Связанные документы:** `_docs/architecture.md` §3.10; `_docs/agent-loop.md` §4.
- **Затрагиваемые файлы:** `app/core/orchestrator.py`, `tests/core/test_orchestrator.py`.

#### Описание

`handle_user_task` достаёт `history = conversations.get_history(user_id)` и передаёт в `Executor.run`. Поскольку адаптер уже вызывает `add_user_message(user_id, text)` **до** `handle_user_task` (`@/home/radif/my/ai_multi_agent_system/app/adapters/telegram/handlers/messages.py:79`), последний элемент `history` — это и есть текущий `goal`. Принимаем такой инвариант: `goal` берётся из `text`, в `messages` подаётся `history` целиком, дубликат не делаем.

#### Definition of Done

- [ ] `core.handle_user_task` достаёт историю и передаёт в executor.
- [ ] Тест `test_orchestrator_passes_history` — мок `Executor`, проверка получения истории.
- [ ] Тест `test_orchestrator_does_not_duplicate_goal` — последний user-message в `history` совпадает с `text`, дубль не появляется.
- [ ] `pytest -q` зелёный.

---

### Задача 1.4. Регрессионный тест диалога

- **Статус:** ToDo
- **Приоритет:** medium
- **Объём:** XS
- **Зависит от:** Задача 1.3
- **Связанные документы:** `_docs/testing.md` §3.4, §3.11.
- **Затрагиваемые файлы:** `tests/test_dialog_memory.py` (новый).

#### Описание

End-to-end тест с моком LLM: имитировать три обмена «Привет, я Радиф / Как меня зовут / Что я говорил?», проверить, что 3-й вызов `llm.chat` получает в `messages` обе предыдущие пары.

#### Definition of Done

- [ ] Тест зелёный, без сетевых вызовов.
- [ ] `pytest -q` зелёный.

---

## 5. Этап 2. Долгосрочная память: авто-подгрузка архива

Цель — сделать `/new`-архив реально полезным: при старте новой сессии релевантные чанки прошлых сессий должны попадать в контекст автоматически.

### Задача 2.1. Спецификация авто-подгрузки

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** Задача 1.1
- **Связанные документы:** `_docs/memory.md` §3, §5; `_docs/architecture.md` §3.10.
- **Затрагиваемые файлы:** `_docs/memory.md`, `_docs/architecture.md`, `_docs/stack.md`, `.env.example`.

#### Описание

Зафиксировать дизайн: при первом сообщении новой сессии (в `core.handle_user_task`, если `len(history) == 1`) делается embed запроса → `SemanticMemory.search(top_k=SESSION_BOOTSTRAP_TOP_K, scope_user_id=user_id)`; найденные чанки склеиваются в один `system`-message `«Контекст из прошлых сессий: …»` и подмешиваются в начало истории (после основного system-prompt). Контролируется флагом `SESSION_BOOTSTRAP_ENABLED` и параметром `SESSION_BOOTSTRAP_TOP_K`.

Альтернатива (если решим иначе по обсуждению с пользователем): не подгружать автоматически, а только усилить инструкцию в `_prompts/agent_system.md` и положиться на tool `memory_search`. Решение фиксируется здесь.

#### Definition of Done

- [ ] `_docs/memory.md` — новый раздел «§3.6 Авто-подгрузка архива в новую сессию».
- [ ] `_docs/stack.md` §9 — добавлены `SESSION_BOOTSTRAP_ENABLED`, `SESSION_BOOTSTRAP_TOP_K`.
- [ ] `.env.example` — новые параметры.
- [ ] Тесты: n/a (документация).

---

### Задача 2.2. Реализация авто-подгрузки + тесты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** M
- **Зависит от:** Задача 1.3, Задача 2.1
- **Связанные документы:** `_docs/memory.md` §3.6 (новый); `_docs/testing.md` §3.7.
- **Затрагиваемые файлы:** `app/core/orchestrator.py` (или новый `app/services/session_bootstrap.py`), `app/config.py`, `tests/core/test_orchestrator.py`, `tests/services/test_session_bootstrap.py`.

#### Описание

Реализовать модуль `SessionBootstrap` (или функцию в `orchestrator`), который при первом сообщении новой сессии делает embed + `search` + форматирование `system`-message. Падение `SemanticMemory` или `embed` — `WARNING`, основной ход не страдает (сессия стартует без авто-контекста).

#### Definition of Done

- [ ] Реализация по спецификации задачи 2.1.
- [ ] `Settings`-валидаторы для новых полей.
- [ ] Тесты: успешная подгрузка; пустой архив (graceful no-op); падение embed/search → `WARNING`, ход продолжается; флаг `SESSION_BOOTSTRAP_ENABLED=false` отключает поведение.
- [ ] `pytest -q` зелёный.

---

## 6. Этап 3. Файловые входы

Цель — принимать `Photo` / `Voice` / `Document` и подключать их в агентный цикл. Все файлы скачиваются во временный путь, удаляются после обработки.

### Задача 3.1. Утилита загрузки файла из Telegram + лимиты

- **Статус:** ToDo
- **Приоритет:** high
- **Объём:** S
- **Зависит от:** —
- **Связанные документы:** `_docs/architecture.md`, `_docs/stack.md` §9, `_docs/requirements.md`.
- **Затрагиваемые файлы:** `app/adapters/telegram/files.py` (новый), `app/config.py`, `.env.example`, `tests/adapters/telegram/test_files.py` (новый).

#### Описание

Async-утилита `download_telegram_file(bot, file_id, *, max_size_mb) -> Path`. Проверяет `file_size` до скачивания, кидает `FileTooLarge` (новое исключение) при превышении. Скачивает в `tempfile.NamedTemporaryFile` с auto-cleanup-контекст-менеджером.

#### Definition of Done

- [ ] Утилита реализована, лимит конфигурируется через `TELEGRAM_MAX_FILE_MB`.
- [ ] Тесты: успех, превышение лимита, ошибка скачивания.
- [ ] `pytest -q` зелёный.

---

### Задача 3.2. Tool `read_document` (PDF/TXT/MD)

- **Статус:** ToDo
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
- **Зависит от:** все задачи Этапа 1–3
- **Связанные документы:** `_docs/architecture.md`, `_docs/commands.md`, `_docs/requirements.md`, `_docs/current-state.md`, `_docs/roadmap.md`, `README.md`, `_board/progress.txt`.
- **Затрагиваемые файлы:** перечисленные документы.

#### Описание

Свести изменения в обзорную форму: `architecture.md` (новый поток с файлами), `commands.md` (раздел «Файлы»), `requirements.md` (FR на медиа), `current-state.md` (актуальное состояние), `roadmap.md` (Этап 7 помечен как частично закрытый Спринтом 02), `README.md` (раздел «Возможности»). В `_board/progress.txt` — чек-лист приёмки Спринта 02.

#### Definition of Done

- [ ] Все перечисленные документы обновлены.
- [ ] Чек-лист в `progress.txt` заполнен.
- [ ] Тесты: n/a (документация).

---

## 7. Риски и смягчение

| # | Риск | Смягчение |
|---|------|-----------|
| 1 | `qwen3.5:4b` плохо тянет длинный контекст из истории + авто-подгруженного архива | Жёсткие лимиты: `HISTORY_MAX_MESSAGES`, `MEMORY_SEARCH_TOP_K`, `MAX_TOOL_OUTPUT_CHARS`. При желании — переключение на модель с большим контекстом через `.env`. |
| 2 | `faster-whisper` тяжёлая зависимость (200+ MB моделей) | Делаем опциональной (`pip install` руками); при отсутствии — handler `Voice` отвечает понятным сообщением. |
| 3 | Vision-модель локально неустановлена | Аналогично: `VISION_MODEL` пуст → fallback. Тесты не требуют реальной модели. |
| 4 | PDF с защитой / сканом (без текстового слоя) | `pypdf` извлечёт пустую строку; tool возвращает `ToolError("PDF не содержит текстового слоя")`. OCR — вне скоупа. |
| 5 | Большие файлы → таймаут / переполнение памяти | `TELEGRAM_MAX_FILE_MB` (default 20). Проверка до скачивания. |
| 6 | Авто-подгрузка архива не относится к новому запросу (false positive) | Подмешиваем как `system`-сообщение, не как user-факт; модель в промпте инструктируется «использовать только если релевантно». В крайнем случае — флаг `SESSION_BOOTSTRAP_ENABLED=false`. |
| 7 | Исторические тесты сломаются от новых параметров `Executor.run` | Сделать `history` опциональным с `None` по умолчанию; обновить только тесты, явно проверяющие новое поведение. |

## 8. Сводная таблица задач спринта

| #   | Задача                                              | Приоритет | Объём | Статус | Зависит от                  |
|-----|------------------------------------------------------|:---------:|:-----:|:------:|------------------------------|
| 1.1 | Спецификация склейки истории                         | high      | S     | ToDo   | —                            |
| 1.2 | `Executor.run` принимает `history`                   | high      | S     | ToDo   | 1.1                          |
| 1.3 | `core.handle_user_task` пробрасывает историю         | high      | S     | ToDo   | 1.2                          |
| 1.4 | Регрессионный тест диалога                           | medium    | XS    | ToDo   | 1.3                          |
| 2.1 | Спецификация авто-подгрузки архива                   | high      | S     | ToDo   | 1.1                          |
| 2.2 | Реализация авто-подгрузки + тесты                    | high      | M     | ToDo   | 1.3, 2.1                     |
| 3.1 | Загрузка файла из Telegram + лимиты                  | high      | S     | ToDo   | —                            |
| 3.2 | Tool `read_document` (PDF/TXT/MD)                    | high      | M     | ToDo   | 3.1                          |
| 3.3 | Handler `Document`                                   | high      | S     | ToDo   | 3.1, 3.2                     |
| 3.4 | Handler `Voice` (faster-whisper)                     | high      | L     | ToDo   | 3.1                          |
| 3.5 | Handler `Photo` (vision)                             | medium    | M     | ToDo   | 3.1                          |
| 3.6 | Полировка: документация и чек-лист                   | high      | S     | ToDo   | все задачи Этапов 1–3        |

> Обновлять при каждом переходе статуса.

## 9. История изменений спринта

- **2026-04-29** — спринт открыт, ветка `feature/02-memory-and-files` создана от `main` (после merge `feature/mvp-agent` → `main` через PR #1, коммит `4011eed`).
