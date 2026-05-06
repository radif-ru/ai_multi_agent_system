# Агентный цикл

Документ описывает работу Executor — единственного агента MVP. Future-документ для Planner / Critic — отдельный, появится в спринте мульти-агента (см. `roadmap.md` Этап 5).

## 1. Назначение

Executor решает задачу пользователя пошагово, используя инструменты:

```
thought → action (tool call) → observation → thought → action → ... → final_answer
```

Каждый шаг — это одно сообщение `assistant` от LLM в JSON-формате. Цикл управляется кодом (Python), модель только думает и выбирает действия.

## 2. Формат ответа модели (СТРОГО)

Модель в каждом шаге возвращает **ровно один JSON-объект** одного из двух видов.

### 2.1 Шаг с действием

```json
{
  "thought": "Краткое рассуждение, что нужно сделать дальше и почему",
  "action": "<имя инструмента>",
  "args": { "<arg1>": "<value1>", ... }
}
```

- `thought` — обязательное поле, **не пустое**.
- `action` — обязательное, должно быть именем зарегистрированного tool из `{{TOOLS_DESCRIPTION}}`.
- `args` — обязательное (даже если tool не требует параметров — тогда `{}`); должен соответствовать `args_schema` tool'а (см. `tools.md` §2).

### 2.2 Финальный ответ

```json
{
  "final_answer": "Текст для пользователя на естественном языке"
}
```

- `final_answer` — единственное поле, обязательное, не пустое.
- Никаких `thought` / `action` / `args` в финальном ответе **не должно быть**.

### 2.3 Что считается ошибкой парсинга

- Невалидный JSON (синтаксическая ошибка).
- Не объект (массив, строка, число на верхнем уровне).
- Поля одного формата вперемешку с полями другого (`{"thought": ..., "final_answer": ...}` — нельзя).
- `action` указывает на несуществующий tool.
- `args` не проходит валидацию `args_schema`.
- Размер JSON > `AGENT_MAX_OUTPUT_CHARS` (защита от мусора).

Парсер толерантен к markdown-fence обёртке (` ```json ... ``` ` или ` ``` ... ``` `) — она снимается перед парсингом. Это нужно для устойчивости к моделям, которые иногда оборачивают JSON в code-fence.

Все эти случаи поднимают `LLMBadResponse`. Цикл прерывается, пользователю — сообщение «Модель ответила в неожиданном формате, попробуйте ещё раз». Сырой ответ модели идёт в WARNING-лог.

## 3. Системный промпт

Хранится в `_prompts/agent_system.md`. Перед стартом цикла в нём подставляются плейсхолдеры:

- `{{TOOLS_DESCRIPTION}}` — список tools в формате:
  ```
  - calculator(expression: string): Безопасное вычисление арифметического выражения.
  - read_file(path: string): Прочитать содержимое файла из data/.
  - http_request(url: string): GET-запрос к URL, возвращает статус и тело.
  - web_search(query: string, top_k: integer = 5): Поиск через DuckDuckGo.
  - memory_search(query: string, top_k: integer = 5): Поиск в долгосрочной памяти.
  - load_skill(name: string): Загрузить полный текст скилла по имени.
  ```
- `{{SKILLS_DESCRIPTION}}` — список доступных скиллов в формате:
  ```
  - example-summary: Suggest a concise summary of a long text.
  ```

Подробности подмешивания — в `prompts.md` §3.

## 4. Цикл (псевдокод)

```python
async def run(
    self,
    *,
    goal: str,
    user_id: int,
    conversation_id: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    # `history` — копия `ConversationStore.get_history(user_id)`,
    # последний элемент которой — текущий user-message с текстом `goal`
    # (адаптер публикует событие MessageReceived, подписчик которого
    # вызывает `add_user_message`, см. `memory.md` §2.4). Чтобы не дублировать `goal`,
    # добавляем его отдельным элементом только если в конце истории его нет.
    history = list(history or [])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": self._build_system_prompt()},
        *history,
    ]
    if not history or history[-1] != {"role": "user", "content": goal}:
        messages.append({"role": "user", "content": goal})

    # Внутрицикловые `assistant` / `Observation`-сообщения копятся ТОЛЬКО
    # в локальном `messages` и НЕ пишутся в `ConversationStore`.
    # В долгую историю попадает только финальный ответ ассистента
    # (его дописывает адаптер после возврата `Executor.run`).

    for step in range(1, self.settings.agent_max_steps + 1):
        response_text = await self.llm.chat(messages, model=...)
        if len(response_text) > self.settings.agent_max_output_chars:
            raise LLMBadResponse("response too large")

        parsed = parse_agent_response(response_text)  # AgentDecision

        self._log_step(step, parsed, user_id, conversation_id)

        if parsed.kind == "final":
            return parsed.final_answer

        # action step
        try:
            observation = await self.tools.execute(parsed.action, parsed.args, ctx=...)
        except ToolError as exc:
            observation = f"Tool error: {exc}"

        messages.append({"role": "assistant", "content": response_text})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    return self._max_steps_reply()
```

Замечания:

- `observation` уходит как `role: user` с префиксом `Observation:`, чтобы LLM не путала её со своим следующим `thought`. Альтернатива — кастомная роль `tool`, но не все локальные модели её поддерживают одинаково.
- `messages` накапливается. При большом числе шагов он может вырасти; при необходимости в более поздних спринтах добавим in-loop обрезку (`history_max_messages` сейчас не трогает этот рабочий список).

## 5. Защита от бесконечного цикла

| Слой защиты | Параметр / реализация |
|-------------|------------------------|
| **Лимит шагов** | `AGENT_MAX_STEPS` (default 10). По достижении — корректный выход с сообщением. |
| **Лимит размера ответа модели** | `AGENT_MAX_OUTPUT_CHARS` (default 8000). Защищает от взрыва контекста при «галлюцинирующем» выводе. |
| **Таймаут LLM** | `OLLAMA_TIMEOUT` (default 120с) на один вызов. При таймауте → `LLMTimeout`, цикл прерывается. |
| **Невалидный JSON** | `LLMBadResponse` → цикл прерывается. |
| **Неизвестный tool** | `LLMBadResponse` (валидация на этапе парсинга, до вызова tool). |
| **Tool error** | Не прерывает цикл; превращается в `observation` и идёт обратно в LLM (агент сам решит, что делать). |

## 6. Логирование

На каждый шаг пишется одна INFO-строка:

```
INFO step=3 kind=action user=12345 conv=abc-123 tool=web_search dur_ms=412 status=ok
```

При парсинге ошибки:

```
WARNING step=3 kind=parse_error user=12345 conv=abc-123 raw="<truncated raw response>"
```

При выходе по лимиту шагов:

```
INFO step=10 kind=max_steps_exceeded user=12345 conv=abc-123 reason="loop did not converge"
```

Полный JSON ответа модели на каждом шаге пишется в DEBUG (или INFO с пометкой `payload=...`, если включён `LOG_LLM_CONTEXT`).

## 7. Тестируемые свойства цикла

(Чек-лист для `tests/agents/test_executor.py` в Спринте 01.)

- Финальный ответ на первом шаге → возвращается без вызова tools.
- Финальный ответ на N-м шаге → tools вызывались N-1 раз, передача `observation` корректная.
- Битый JSON → `LLMBadResponse`, цикл не вылетает в `Exception`, пользователь получает понятное сообщение.
- Неизвестный `action` → `LLMBadResponse`, цикл не вылетает.
- Tool падает (`raise ToolError`) → `observation` содержит «Tool error: ...», цикл идёт дальше.
- Превышение `AGENT_MAX_STEPS` → корректный выход, специфичное сообщение пользователю.
- Превышение `AGENT_MAX_OUTPUT_CHARS` → `LLMBadResponse`.
- Корректное логирование шагов (через мок `logger.info` / `caplog`).

## 8. Будущие расширения цикла

(Сейчас НЕ реализуем; кандидаты в `roadmap.md`.)

- **Стриминг шагов**: показывать пользователю «Шаг N: <thought>…» в виде edit'а исходящего сообщения (Этап 3).
- **Параллельные действия**: разрешить `action` массив (несколько tools параллельно). Требует другой контракт ответа модели — отдельный спринт.
- **Reflection-loop**: после `final_answer` запускать Critic; если он `REVISE` — возвращать в цикл с фидбеком (Этап 5 «Multi-agent»).
- **Динамический `AGENT_MAX_STEPS` по сложности задачи**: Planner оценивает сложность и предлагает лимит. Также Этап 5.
