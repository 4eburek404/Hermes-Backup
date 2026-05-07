# Практический инженерный анализ: Enforcement механизмы для LLM tool-use compliance

## Проблема

LLM-агент (Hermes) вызывает `travelpayouts_flight_search` или `fli` напрямую, игнорируя
skill `flight-search`, который предписывает использовать `flights_cli route live-assemble`.
Несмотря на system prompt "MUST load skill if relevant" и память, модель 3/3 раз обходила skill.

---

## Карта кодовой базы (ключевые точки перехвата)

| Файл | Функция/класс | Роль |
|------|--------------|------|
| `model_tools.py:635` | `handle_function_call()` | Главный dispatch — все tool calls проходят здесь |
| `model_tools.py:678-693` | `pre_tool_call_hook` | Plugin hook: можно вернуть `{"action":"block","message":"..."}` |
| `run_agent.py:9102` | `_invoke_tool()` | Агент-level dispatch (agent loop) — дублирует pre_tool_call |
| `run_agent.py:9573-9574` | `pre_tool_call` в sequential path | Вторая точка pre_tool_call |
| `hermes_cli/plugins.py:1086` | `get_pre_tool_call_block_message()` | API для block-директив от плагинов |
| `hermes_cli/plugins.py:61-80` | `VALID_HOOKS` | Все hook types включая `pre_tool_call` |
| `agent/prompt_builder.py:849-876` | `build_skills_system_prompt()` | System prompt секция "Skills (mandatory)" |
| `agent/prompt_builder.py:176-183` | `SKILLS_GUIDANCE` | Guidance по сохранению/обновлению skills |
| `toolsets.py:31-63` | `_HERMES_CORE_TOOLS` | Core tool list (включает `skills_list`, `skill_view`) |
| `tools/skills_tool.py:1457-1474` | `SKILL_VIEW_SCHEMA` | Schema skill_view (description + parameters) |
| `tools/skills_tool.py:849-949` | `skill_view()` | Функция загрузки skill content |
| `plugins/travelpayouts-flights/__init__.py:13-25` | `register(ctx)` | Регистрация travelpayouts tool |
| `plugins/travelpayouts-flights/schemas.py:11-56` | `TRAVELPAYOUTS_FLIGHT_SEARCH_SCHEMA` | Description/tool schema |

---

## Решение 1: Архитектурные (code/framework) — 95%+ compliance

### 1A. `pre_tool_call` plugin hook → guard (★ РЕКОМЕНДУЕМОЕ, простая реализация)

**Точка внедрения**: `model_tools.py:678-693` + `hermes_cli/plugins.py:1086-1122`

Hermes уже имеет механизм блокировки tool calls через плагины. Создаём guard-плагин,
который перехватывает `travelpayouts_flight_search` и блокирует вызов с инструкцией
загрузить skill.

**Реализация** — новый файл `~/.hermes/plugins/flight-skill-guard/__init__.py`:

```python
"""Flight-search skill guard plugin.

Blocks direct calls to travelpayouts_flight_search and forces
skill_view('flight-search') first.

Config (config.yaml):
  skills.flight_guard: true   # default: true when plugin is installed
"""
from __future__ import annotations

# Tool calls that require the flight-search skill to be loaded first
_GUARDED_TOOLS = {"travelpayouts_flight_search"}
_SKILL_NAME = "flight-search"

# Session-level tracking: which sessions have loaded the skill
_loaded_sessions: set[str] = set()


def register(ctx) -> None:
    """Register the flight-search guard hook."""
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)


def _on_pre_tool_call(*, tool_name: str, args: dict | None = None,
                      task_id: str = "", session_id: str = "",
                      tool_call_id: str = "") -> dict | None:
    """Block guarded tools if the skill hasn't been loaded this session."""
    if tool_name not in _GUARDED_TOOLS:
        return None

    if session_id in _loaded_sessions:
        return None  # Skill already loaded this session, allow

    return {
        "action": "block",
        "message": (
            f"BLOCKED: {tool_name} cannot be called directly. "
            f"You MUST call skill_view('{_SKILL_NAME}') first to load "
            f"the flight-search workflow, then follow its Golden Path "
            f"(flights_cli route live-assemble). "
            f"After loading the skill once, {tool_name} will be available "
            f"for debug/fallback purposes."
        ),
    }


def _on_post_tool_call(*, tool_name: str, args: dict | None = None,
                       result: str = "", task_id: str = "",
                       session_id: str = "",
                       tool_call_id: str = "", **kw) -> None:
    """Track when skill_view('flight-search') is called."""
    if tool_name == "skill_view" and args and args.get("name") == _SKILL_NAME:
        _loaded_sessions.add(session_id)
```

**Плюсы**:
- Использует существующий hook-механизм Hermes (0 новых архитектурных изменений)
- Гарантированная блокировка: модель получает error message и вынуждена вызвать skill_view
- Легко расширить на другие tools/skills
- Плагин можно включить/выключить через config

**Минусы**:
- Требует отдельный плагин-каталог
- Session tracking — in-process only (перезапуск сбрасывает, но это ОК — skill нужно загружать каждую сессию)

### 1B. Middleware в `handle_function_call()` — runtime redirect

**Точка внедрения**: `model_tools.py:635-774`, добавить после `coerce_tool_args` (строка 662)

```python
# ── Skill-guarded tool redirect ──
# Tools in this dict are blocked unless the matching skill was loaded
# in the current session.  When blocked, the error message tells the
# model to call skill_view() first.
_SKILL_GUARDS: dict[str, str] = {
    "travelpayouts_flight_search": "flight-search",
    # extend as needed
}

def handle_function_call(function_name, function_args, ...):
    function_args = coerce_tool_args(function_name, function_args)

    # NEW: skill guard check
    if function_name in _SKILL_GUARDS:
        required_skill = _SKILL_GUARDS[function_name]
        if not _is_skill_loaded_in_session(required_skill, session_id):
            return json.dumps({
                "error": (
                    f"BLOCKED: Call skill_view('{required_skill}') before using "
                    f"{function_name}. The skill defines the correct workflow."
                ),
            }, ensure_ascii=False)
    # ... rest of existing code ...
```

**Плюсы**: Ещё проще — right in the dispatch path, минимальная абстракция
**Минусы**: Тесная связь (hardcoded в model_tools), не обобщается легко

### 1C. Условное скрытие tools из tool list

**Точка внедрения**: `_compute_tool_definitions()` в `model_tools.py:327-475` или
через механизм, аналогичный `check_fn` в registry.

В `tools/registry.py` каждый tool может иметь `check_fn` — функцию, которая определяет
доступность tool. Расширить: `check_fn` может учитывать session-level state.

```python
# In plugin registration (plugins/travelpayouts-flights/__init__.py):
def _flight_search_check():
    """Only available after flight-search skill is loaded."""
    from tools.skills_tool import is_skill_loaded_in_session  # NEW helper
    return is_skill_loaded_in_session("flight-search")

ctx.register_tool(
    name="travelpayouts_flight_search",
    toolset="travelpayouts",
    schema=MODIFIED_SCHEMA,  # see Solution 2
    handler=travelpayouts_flight_search,
    check_fn=_flight_search_check,  # Dynamic visibility
    # ...
)
```

**Плюсы**: Tool вообще не появляется в tool list → модель не может его вызвать
**Минусы**: 
  - `check_fn` сейчас кэшируется с TTL 30s — нужно обновлять при skill_view
  - Нарушает "tool always visible, just guarded" принцип
  - Сложнее отлаживать (tool может "исчезать" неожиданно)

---

## Решение 2: Prompt Engineering — 70-85% compliance (дополнение к 1A)

### 2A. Изменить описание `travelpayouts_flight_search` schema

**Точка внедрения**: `plugins/travelpayouts-flights/schemas.py:13-21`

Текущее описание:
```
"Search cached Travelpayouts/Aviasales flight prices for one city/airport
route and exact departure date..."
```

Заменить на:
```python
TRAVELPAYOUTS_FLIGHT_SEARCH_SCHEMA = {
    "name": "travelpayouts_flight_search",
    "description": (
        "⚠️ DO NOT USE THIS TOOL FOR ROUTE SEARCHES — use flights_cli route "
        "live-assemble via the 'flight-search' skill instead (call "
        "skill_view('flight-search') first). This tool returns cached "
        "Travelpayouts/Aviasales prices ONLY as a fallback for price "
        "validation after the CLI has been run, or when specifically asked "
        "for cached-only advisory prices. It cannot assemble routes, "
        "validate connections, or rank options. For any multi-segment or "
        "business travel search, the CLI is mandatory.\n\n"
        "origin/destination: 3-letter IATA code..."
    ),
    # ...
}
```

**Ключевой принцип**: Описание tool — ближайший контекст к точке выбора модели.
Модель читает description при выборе tool из списка. Предупреждение В description
срабатывает лучше, чем в system prompt на 2 уровня выше.

### 2B. Усиление system prompt "Skills (mandatory)" секции

**Точка внедрения**: `agent/prompt_builder.py:849-876`

Текущий prompt (строка 850-875) уже содержит:
> "If a skill matches or is even partially relevant to your task, you MUST
> load it with skill_view(name) and follow its instructions."

Добавить конкретный пример-ограничение:
```python
result = (
    "## Skills (mandatory)\n"
    "Before replying, scan the skills below. If a skill matches or is even partially relevant "
    "to your task, you MUST load it with skill_view(name) and follow its instructions. "
    # ... existing text ...
    "CRITICAL: When a skill specifies tools you must NOT use (e.g., 'Do not call "
    "travelpayouts_flight_search, use flights_cli instead'), those prohibitions are "
    "absolute — they override the tool list. A tool being available does NOT mean "
    "you should use it if a loaded skill says otherwise.\n"
    "\n"
    # ... rest
)
```

### 2C. Two-shot examples в system prompt

Добавить в `build_skills_system_prompt()` или в `TOOL_USE_ENFORCEMENT_GUIDANCE`:

```python
# Example: flight search
# User: "Find flights SVX→IST August 14"
# AI: skill_view('flight-search')  ← MUST DO THIS FIRST
# AI: [reads skill, follows Golden Path with flights_cli]
# AI: [presents results from CLI recommendations]
# WRONG: travelpayouts_flight_search(origin="SVX", destination="IST", ...)
```

---

## Решение 3: Skill Design — 85-90% compliance (в комбинации с 1A)

### 3A. Skill как guardrail — модификация tool list при загрузке skill

При `skill_view('flight-search')`, помимо возврата контента, модифицировать session state,
который делает `travelpayouts_flight_search` доступным (см. Решение 1C).

**Точка внедрения**: `tools/skills_tool.py:849` — функция `skill_view()`

Добавить в `_skill_view_with_bump()` (строка 1486):
```python
def _skill_view_with_bump(args, **kw):
    result = skill_view(args.get("name", ""), args.get("file_path"), ...)
    # NEW: Notify guard system that this skill was loaded
    _name = args.get("name", "")
    if _name in _SKILL_GUARDS_REVERSE:  # {"flight-search": ["travelpayouts_flight_search"]}
        _mark_skill_loaded_in_session(_name, kw.get("session_id", ""))
    # ... existing bump code ...
```

### 3B. Skill pre-condition — без skill_view tool заблокирован

Это по сути Решение 1A + 3A вместе. Конкретная реализация:

1. Guard-плагин (1A) блокирует `travelpayouts_flight_search`
2. `skill_view('flight-search')` автоматически регистрирует "skill loaded" 
3. Последующие вызовы `travelpayouts_flight_search` проходят

---

## Решение 4: Memory/fact_store — 40-60% compliance (слабое, вспомогательное)

### 4A. Hard fact в memory store

```
"FLIGHT SEARCH ROUTING: ALWAYS call skill_view('flight-search') before ANY flight search. 
travelpayouts_flight_search is BLOCKED for route searches. Use flights_cli route live-assemble."
```

**Проблема**: Memory facts загружаются в каждый session, но модель всё равно
может игнорировать их в пользу "удобного" tool call. Memory — declarative context,
не enforcement.

### 4B. Entity linking

Связать entity "flight search" → "skill_view('flight-search')" в fact store.
Модель видит связь, но enforcement остаётся мягким.

**Вердикт**: Memory решения ПОЛЕЗНЫ как вспомогательный слой, но НЕ достаточны
как основное enforcement решение. Модель уже видела "Do not call travelpayouts_flight_search"
в skill content и игнорировала.

---

## Решение 5: Комбинированный анализ — конкретный план

### Приоритизация

| Приоритет | Решение | Ожидаемый compliance | Сложность | Время |
|-----------|---------|---------------------|-----------|-------|
| **P0** | 1A: pre_tool_call guard plugin | **95%+** | Низкая | 1 час |
| **P1** | 2A: Изменить tool description | **+10-15%** | Минимальная | 15 мин |
| **P1** | 2B: Усилить system prompt | **+5-10%** | Минимальная | 15 мин |
| **P2** | 3A/3B: Skill↔guard интеграция | **Делает 1A полным** | Низкая | 30 мин |
| **P3** | 4A: Memory hard fact | **+5%** | Минимальная | 5 мин |
| **P3** | 2C: Two-shot examples | **+5%** | Низкая | 30 мин |

### Почему P0 = 95%+ ?

**pre_tool_call guard** работает потому что:

1. Модель вызывает `travelpayouts_flight_search` → получает **JSON error** с сообщением
   "BLOCKED: Call skill_view('flight-search') first"
2. Модель видит error в tool results → единственный путь вперёд — вызвать `skill_view`
3. После `skill_view` → skill content загружен → модель видит Golden Path
4. Guard позволяет последующий вызов `travelpayouts_flight_search` (для debug/fallback)
5. **Модель не может обойти block** — это runtime enforcement, не prompt suggestion

Единственный способ обойти: модель не вызывает ни tool, а отвечает текстом.
Но TOOL_USE_ENFORCEMENT_GUIDANCE уже требует tool use, и ошибка явно говорит
что делать.

---

## Конкретный план реализации

### Шаг 1: Создать flight-skill-guard плагин (P0)

```
~/.hermes/plugins/flight-skill-guard/
├── __init__.py          # register() + hooks
├── plugin.yaml          # metadata
└── README.md            # documentation
```

### Шаг 2: Изменить travelpayouts schema (P1)

Файл: `~/.hermes/plugins/travelpayouts-flights/schemas.py`
Заменить description на версию с ⚠️ WARNING.

### Шаг 3: Усилить system prompt (P1)

Файл: `agent/prompt_builder.py:849-876`
Добавить "CRITICAL: When a skill specifies tools you must NOT use..."

### Шаг 4: Интегрировать skill_view → guard state (P2)

Файл: `tools/skills_tool.py:1486-1514`
В `_skill_view_with_bump()` — уведомлять guard о загрузке skill.

### Шаг 5: Memory hard fact (P3)

Добавить через `memory_tool`:
```
"FLIGHT SEARCH ROUTING: ALWAYS skill_view('flight-search') before any flight tool call.
BLOCKED: travelpayouts_flight_search for route searches."
```

---

## Альтернативный "nuclear" вариант: удалить tool из toolset

Если compliance критичен и fallback на travelpayouts не нужен:

В `~/.hermes/plugins/travelpayouts-flights/__init__.py` — закомментировать
`ctx.register_tool(...)`. Tool не появится в schema → модель не сможет вызвать.

Это **100% compliance**, но теряется fallback-возможность travelpayouts для
debug/validation. Рекомендуется только если skill Golden Path полностью
покрывает все варианты использования.

---

## Выводы

1. **Prompt engineering один** не даёт 95%+ compliance — модель видит tool в list
   и выбирает "удобный" путь, игнорируя soft constraints на 3 уровня выше
2. **Runtime enforcement через pre_tool_call hook** — единственный механизм
   с гарантированным compliance в архитектуре Hermes
3. **Комбинация P0+P1+P2** = 95%+ compliance при минимальных затратах
4. Все решения совместимы друг с другом — наслаиваются для defense-in-depth