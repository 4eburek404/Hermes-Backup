# Plan: Установка и настройка Holographic Memory

**Date:** 2026-04-28
**Status:** done ✓
**Goal:** Активировать Holographic memory provider с ручным курированием (auto_extract: false) и проверить работу.

## Context

Текущее состояние:
- `memory.provider: ''` — только built-in память (MEMORY.md + USER.md)
- Плагин `holographic` установлен (0.1.0) в `/home/konstantin/.hermes/hermes-agent/plugins/memory/holographic/`
- Зависимости: SQLite (всегда доступен), NumPy — опционально для HRR-алгебры
- Хук: `on_session_end`
- Дополнительные инструменты, которые плагин добавляет агенту: `fact_store` (9 действий: add, search, probe, related, reason, contradict, update, remove, list) и `fact_feedback` (helpful/unhelpful)

## Non-goals

- Не включать `auto_extract: true` — пользователь предпочитает ручное курирование
- Не трогать другие memory-провайдеры (honcho, mem0, etc.)
- Не менять текущую структуру built-in памяти

## Steps

### 1. Проверить наличие NumPy (опционально, но желательно)

```bash
python3 -c "import numpy; print(numpy.__version__)"
```

Если нет — HRR-алгебра (probe, related, reason, contradict) будет недоступна, но FTS5-поиск и факты будут работать.

### 2. Сделать бэкап текущего конфига

```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d-%H%M%S)
```

### 3. Установить Holographic как memory-провайдер

```bash
hermes config set memory.provider holographic
```

### 4. Проверить и при необходимости скорректировать plugin-конфиг в config.yaml

Плагин читает секцию `plugins.hermes-memory-store` из `config.yaml`. Параметры по умолчанию:

| Параметр | Значение по умолчанию | Что делает |
|---|---|---|
| `db_path` | `$HERMES_HOME/memory_store.db` | Путь к SQLite-базе |
| `auto_extract` | `false` | **Оставляем false** — без авто-извлечения |
| `default_trust` | `0.5` | Начальный trust score для новых фактов |
| `hrr_dim` | `1024` | Размерность HRR-векторов |

Убедиться, что `auto_extract` точно `false`:

```bash
hermes config set plugins.hermes-memory-store.auto_extract false
```

### 5. Перезапустить Hermes (новый сеанс — /reset)

Изменения `memory.provider` требуют нового сеанса. В gateway: `/restart`. В CLI: новый `hermes`.

### 6. Проверить статус

```bash
hermes memory status
```

Ожидаемый вывод: `Provider: holographic (local)`.

### 7. Функциональный тест (в новой сессии)

Выполнить последовательно в чате с Hermes:

1. **Добавить факт:**
   ```
   fact_store(action='add', content='Konstantin uses Hermes with deepseek-v4-pro:cloud via ollama-local', category='general')
   ```
   → Ожидаемый ответ: `{"fact_id": 1, "status": "added"}`

2. **Поиск по ключевым словам:**
   ```
   fact_store(action='search', query='deepseek ollama')
   ```
   → Должен найти факт #1

3. **Проверить список:**
   ```
   fact_store(action='list')
   ```
   → Должен показать все факты

4. **Probe по сущности:**
   ```
   fact_store(action='probe', entity='Konstantin')
   ```
   → Должен найти факт про Константина (требуется NumPy)

5. **Обратная связь:**
   ```
   fact_feedback(action='helpful', fact_id=1)
   ```
   → Trust должен вырасти с 0.5 до 0.55

### 8. Проверить БД физически

```bash
sqlite3 ~/.hermes/memory_store.db "SELECT fact_id, substr(content,1,80), trust_score, category FROM facts;"
sqlite3 ~/.hermes/memory_store.db "SELECT name, entity_type FROM entities;"
```

## Verification

- [ ] `hermes memory status` показывает `Provider: holographic`
- [ ] `fact_store(action='add', ...)` возвращает fact_id
- [ ] `fact_store(action='search', ...)` находит добавленный факт
- [ ] `fact_store(action='list')` показывает все факты с trust_score
- [ ] `fact_feedback` меняет trust_score
- [ ] База `memory_store.db` физически существует и содержит таблицы `facts`, `entities`, `facts_fts`
- [ ] `auto_extract: false` — факты не создаются без явного вызова `fact_store(action='add')`

## Risks / Pitfalls

- **HRR без NumPy:** probe/related/reason/contradict молча падают в FTS5-поиск (graceful degradation). Это не ошибка, но ослабляет функциональность.
- **Дубликаты:** `add_fact` имеет `UNIQUE` на `content` — одинаковый контент вернёт существующий fact_id без ошибки.
- **Контекстное окно:** `system_prompt_block()` плагина добавляет короткий блок про Holographic в system prompt (~100 токенов), что несущественно.
- **Откат:** `hermes config set memory.provider ''` + `/reset` полностью отключает Holographic, база остаётся на диске.

## Notes

- Holographic **дополняет** built-in память, не заменяет. Built-in MEMORY.md/USER.md продолжает работать как always-in-context.
- Факты из Holographic инжектятся в контекст только через `prefetch()` или явные tool calls — не раздувают контекст.
- Плагин также зеркалит built-in `memory add` через `on_memory_write()` — факты создаются автоматически при обычных вызовах `memory()`.
