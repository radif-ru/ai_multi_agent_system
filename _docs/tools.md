# Инструменты (tools)

Документ описывает контракт инструмента, текущий MVP-набор и порядок добавления нового tool. Связанные документы: `architecture.md` §3.7, `agent-loop.md` §2, `requirements.md` §1.3.

## 1. Что такое tool

**Tool** — функция, которую агент вызывает в шаге `action` цикла `thought → action → observation`. Один tool = одна возможность сделать что-то за пределами LLM (посчитать, прочитать файл, сходить в сеть, поискать в памяти и т. д.).

Каждый tool — отдельный модуль в `app/tools/<name>.py`. Регистрация — централизованная в `app/tools/registry.py`. Описание автоматически попадает в системный промпт (плейсхолдер `{{TOOLS_DESCRIPTION}}`, см. `prompts.md` §3).

## 2. Контракт tool

Базовый класс — `app/tools/base.py::Tool`:

```python
from typing import Any, Mapping, Protocol

class ToolContext(Protocol):
    """Зависимости, доступные tool'у в момент выполнения."""
    user_id: int
    chat_id: int
    conversation_id: str
    settings: "Settings"
    llm: "OllamaClient"
    semantic_memory: "SemanticMemory"
    skills: "SkillRegistry"


class Tool(Protocol):
    name: str            # snake_case, уникальное в реестре
    description: str     # одна короткая строка, попадает в системный промпт
    args_schema: Mapping[str, Any]  # JSON Schema (object с properties и required)

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str: ...
```

Возврат — **строка**: то, что станет `observation` в следующем шаге цикла. Ошибка — поднимается как `ToolError(message)` (см. `app/tools/errors.py`).

### 2.1 Правила реализации

- **Один tool — один файл.** Никаких комбинированных модулей.
- **`run` — async**, даже если работа синхронная (для единого контракта).
- **Никаких сетевых вызовов в `__init__`.** Конструктор только сохраняет зависимости.
- **Аргументы валидируются по `args_schema`** до вызова `run`. Ответственность — на `ToolRegistry.execute`.
- **Большие ответы обрезаются** до `MAX_TOOL_OUTPUT_CHARS` (значение фиксируется в `app/tools/base.py`, default — 4000 символов). Усечение — суффиксом `... [truncated]`.
- **Логирование**: tool сам **не пишет** свои логи; их пишет реестр (`tool=<name> dur_ms=<n> status=ok|error`). Внутри tool можно использовать `logger.debug` для деталей.

### 2.2 Пример (упрощённый calculator)

```python
# app/tools/calculator.py
import ast
import operator
from typing import Mapping, Any
from app.tools.base import Tool, ToolContext
from app.tools.errors import ToolError

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ToolError(f"Unsupported expression: {ast.dump(node)!r}")


class CalculatorTool:
    name = "calculator"
    description = "Безопасное вычисление арифметического выражения (без eval/exec)."
    args_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    async def run(self, args: Mapping[str, Any], ctx: ToolContext) -> str:
        expression = str(args["expression"])
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ToolError(f"Syntax error: {exc.msg}") from exc
        result = _safe_eval(tree.body)
        return str(result)
```

## 3. Реестр (`app/tools/registry.py`)

```python
class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None: ...

    def get(self, name: str) -> Tool: ...
    def list_descriptions(self) -> list[dict]:
        """Возвращает [{name, description, args_schema}, ...] для системного промпта."""
    async def execute(
        self, name: str, args: Mapping[str, Any], ctx: ToolContext
    ) -> str:
        """1) Найти tool. 2) Валидировать args. 3) Запустить. 4) Логировать. 5) Усечь output."""
```

`execute` — единственная точка входа из Executor. Все ошибки (`ToolNotFound`, `ArgsValidationError`, `ToolError`) логируются и возвращаются как `Tool error: ...`-строка (а не как exception); цикл агента не прерывается, агент сам решит, что делать дальше.

## 4. MVP-набор инструментов

### 4.1 `calculator`

- **Описание:** Безопасное вычисление арифметического выражения (без `eval`/`exec`).
- **Args:** `{"expression": "<строка>"}`.
- **Return:** строка с результатом (`"1158"`, `"3.14"` и т. п.).
- **Реализация:** AST-парсинг + whitelisted операторы (`+ - * / ** % unary +/-`). Никаких функций / переменных / атрибутов.
- **Ошибки:** синтаксическая ошибка → `ToolError`; деление на ноль → `ToolError`.

### 4.2 `read_file`

- **Описание:** Прочитать содержимое файла из разрешённых каталогов (по умолчанию `data/`).
- **Args:** `{"path": "<строка>"}`.
- **Return:** содержимое файла (UTF-8), усечённое до `MAX_TOOL_OUTPUT_CHARS`.
- **Реализация:** валидация пути (`Path.resolve()` должен начинаться с одного из путей whitelist'а из `Settings`); запрет `..`; запрет симлинков, которые ведут наружу; ограничение размера файла (`MAX_FILE_BYTES`, default 1 MiB).
- **Ошибки:** путь вне whitelist → `ToolError("path not allowed")`; файла нет → `ToolError("file not found")`; файл бинарный → `ToolError("binary file not supported")`.

### 4.3 `http_request`

- **Описание:** GET-запрос к URL, возврат статуса и тела.
- **Args:** `{"url": "<строка>"}`.
- **Return:** строка вида `"HTTP 200\n<тело усечённое>"`.
- **Реализация:** `httpx.AsyncClient.get(url, timeout=...)`; только GET; только http/https; редиректы — следуем (max_redirects=3); response body режется до `MAX_TOOL_OUTPUT_CHARS`.
- **Ошибки:** не http/https → `ToolError`; таймаут → `ToolError`; 4xx/5xx — НЕ ошибка, возвращается как часть строки (агент сам решит).

### 4.4 `web_search`

- **Описание:** Веб-поиск через DuckDuckGo (без API-ключей).
- **Args:** `{"query": "<строка>", "top_k": <int, default 5>}`.
- **Return:** JSON-строка `[{"title": "...", "href": "...", "snippet": "..."}, ...]`.
- **Реализация:** библиотека `ddgs` (бывшая `duckduckgo-search`), синхронный API оборачиваем `asyncio.to_thread`.
- **Ошибки:** сетевая недоступность → `ToolError("search unavailable")`; пустой результат → возвращается `[]` (НЕ ошибка).

### 4.5 `memory_search`

- **Описание:** Поиск в долгосрочной семантической памяти (саммари прошлых сессий).
- **Args:** `{"query": "<строка>", "top_k": <int, default из MEMORY_SEARCH_TOP_K>}`.
- **Return:** JSON-строка `[{"text": "...", "conversation_id": "...", "created_at": "...", "distance": 0.42}, ...]`.
- **Реализация:** `OllamaClient.embed(query)` → `SemanticMemory.search(embedding, top_k, scope_user_id=ctx.user_id)`. Подробности — `memory.md` §3.4.
- **Ошибки:** долгосрочная память не инициализирована (sqlite-vec не загрузился) → `ToolError("long-term memory unavailable")`; пустой результат → `[]`.

### 4.6 `load_skill`

- **Описание:** Загрузить полный текст скилла по имени из `_skills/`.
- **Args:** `{"name": "<строка>"}`.
- **Return:** содержимое `SKILL.md` без первой строки (которая `Description: ...` уже инжектирована в промпт).
- **Реализация:** `ctx.skills.get_body(name)`. Если скилла нет — `ToolError("skill not found: <name>")`.

### 4.7 `describe_image`

- **Описание:** Повторно описать изображение по пути к файлу. Используется для уточнения деталей после первичного описания.
- **Args:** `{"image_path": "<строка>", "caption": "<строка, optional>"}`.
- **Return:** описание изображения от vision-модели.
- **Реализация:** валидация пути (должен быть в `tmp/`, без `..`, существующий файл изображения); вызов `Vision.describe(image_path, caption)`. Путь к файлу сохраняется в `tmp/` и не удаляется сразу — живёт до `/new` или TTL cleanup (1 час).
- **Ошибки:** путь вне `tmp/` → `ToolError("path not allowed")`; файла нет → `ToolError("file not found")`; не изображение → `ToolError("not an image file")`; LLM недоступна → `ToolError("LLM unavailable for vision")`.

### 4.8 `weather`

- **Описание:** Получить погоду для города/локации через wttr.in с fallback на веб-поиск.
- **Args:** `{"location": "<строка>"}` (город, регион или код аэропорта).
- **Return:** текущая погода от wttr.in или результаты веб-поиска при недоступности сервиса.
- **Реализация:** использует `curl` для запроса к wttr.in (формат 0 для подробных условий); при ошибке сети или недоступности wttr.in автоматически использует `WebSearchTool` для поиска погоды; пробелы в локации заменяются на `+` для URL.
- **Ошибки:** неизвестная локация → `ToolError("Неизвестная локация: <location>")`; curl не установлен и веб-поиск недоступен → `ToolError("Сервис wttr.in недоступен и веб-поиск также не удался")`.

## 5. Как добавить новый tool

1. Создать `app/tools/<name>.py` по контракту §2.
2. Зарегистрировать инстанс в `app/tools/registry.py` (в составе `_DEFAULT_TOOLS`).
3. Описание попадёт в `{{TOOLS_DESCRIPTION}}` системного промпта **автоматически** при следующем старте процесса.
4. Покрыть unit-тестом `tests/tools/test_<name>.py`:
   - валидный вызов → ожидаемый результат;
   - невалидные `args` → `ArgsValidationError` (через registry);
   - типичная ошибка домена → `ToolError`;
   - усечение длинного output'а до `MAX_TOOL_OUTPUT_CHARS`.
5. Если tool требует новые env-переменные — обновить `.env.example`, `Settings`, `_docs/stack.md` §9.
6. Если tool требует новой зависимости — обновить `requirements.txt` и `_docs/links.md`.

## 6. Что НЕ tool, а skill

Если задача — *«как именно решать класс задач»* (последовательность мыслей, шаблон формата, набор правил), это **skill**, а не tool. Skill живёт в `_skills/<name>/SKILL.md`, его агент подгружает через tool `load_skill`. См. `skills.md` §1 «Когда tool, а когда skill».

## 7. Безопасность

Все tools в MVP — **локальные**: `calculator`, `read_file` (whitelist каталогов), `http_request` (без bearer-токенов / cookies), `web_search` (только DuckDuckGo), `memory_search` (свой `.db`), `load_skill` (только `_skills/`).

В будущих спринтах появятся tools, требующие настоящего sandboxing'а (например, выполнение shell-команд, чтение из произвольного места ФС, запись в БД). Они будут идти отдельным контрактом `SandboxedTool` (см. `roadmap.md` Этап 13).

## 8. Не-цели MVP

(Кандидаты в `roadmap.md`.)

- Параллельное выполнение нескольких tools за один шаг.
- Стриминг результатов tool в Telegram.
- MCP (Model Context Protocol) совместимость для внешних tool-серверов.
- Генерация tool из OpenAPI-схемы / autopilot.
