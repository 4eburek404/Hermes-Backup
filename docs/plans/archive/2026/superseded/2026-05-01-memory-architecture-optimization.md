# План: Оптимизация архитектуры знаний MEMORY.md

**Дата создания:** 2026-05-01
**Статус:** superseded
**Контекст:** Аудит всех слоёв знаний (MEMORY, USER, SOUL, fact_store, docs, skills) → предложение нового MEMORY.md

## Status

Current status: superseded

## Notes

Superseded on 2026-05-03 by `/home/konstantin/docs/plans/archive/2026/done/memory-architecture-optimization.md`, which completed the approved compact revisions of `MEMORY.md`, `USER.md`, and `SOUL.md`.

## Проблема

Текущий MEMORY.md (2253 байта, 11 записей) содержит:
- Избыточные записи (§9 дублирует §2)
- Детали, которые лучше живут в docs/skills/fact_store (§4 ollama ENOSPC, §8 credentials detail)
- Отсутствующие критические guardrails (Gmail personal-only, факт/гипотеза, bare commands, JSON Ollama Cloud)
- Дубликаты между MEMORY и fact_store (#73, #74, #75, #65)

## Предлагаемое изменение

### Новый MEMORY.md (11 пунктов, ~1200 символов)

```text
§ Docs: /home/konstantin/docs/ — infrastructure.md, runbooks.md, user-context.md, plans/. Читать релевантный файл перед изменениями.
§ Hindsight ≠ Holographic: не переносить негативный опыт с одной системы/инструмента на другой без верификации. Оценивать по текущему поведению.
§ Не перенос confident conclusions на косвенных данных — всегда маркировать: факт / гипотеза / требуется проверка.
§ Gmail ks.orlov@gmail.com — строго личный; рабочие письма и автоматизации туда не привязывать.
§ Точная атрибуция: timezone, config, ACL/scope, credential shape — называть причину по имени, не списывать на «баг модели».
§ Context-switch: нотификация B во время A → спросить до переключения.
§ Execution gate: перед batch-операцией с внешним состоянием перечитать релевантную секцию skill.
§ Preemptive corrections: ollama run/pull :cloud = ENOSPC → HTTP API only. Cron timezone ≠ user timezone → проверять date. JSON Ollama Cloud: json_object + English system prompt, не json_schema.
§ НЕ сохранять секреты и credential paths нигде: ни в docs, ни в памяти, ни в чате. Pasted tokens = compromised → revoke.
§ DO-NOT-EDIT: MEMORY.md, USER.md, SOUL.md — только с явного разрешения. Diff перед изменением.
§ MEMORY = ядро + указатели. Атомарные факты → fact_store. Процедуры → skills. Детали → docs. Holographic: search before add → update, не duplicate.
```

### Удалить из fact_store (дублируют MEMORY)

| fact_id | Содержание | Дублирует |
|---|---|---|
| #73 | DO-NOT-EDIT guardrail | MEMORY §10 |
| #75 | DO-NOT-EDIT guardrail (дубликат) | MEMORY §10 |
| #74 | Holographic hygiene | MEMORY §11 + SOUL.md |
| #65 | Pasted tokens = compromised | MEMORY §9 |

### Обновить в fact_store

| fact_id | Изменение |
|---|---|
| #8 | Добавить ссылку: "Guardrail: Gmail personal-only → MEMORY §4" |
| #16 | Добавить ссылку: "Short trigger → MEMORY §7" |
| #20 | Добавить ссылку: "Hard constraint → MEMORY §4" |

### Что удалено из текущего MEMORY и куда ушло

| Было в MEMORY | Куда |
|---|---|
| §2 Docs указатель (старый) + §9 Планы | Слито → §1 (единый указатель) |
| §3 Cron pin+timezone (деталь) | Procedure → runbooks.md; short rule → §8 |
| §4 ollama run ENOSPC | short trigger → §8; detail → runbooks/skill |
| §8 Credentials + Gmail detail | Gmail guardrail → §4; secrets → §9; config detail → docs/fact_store |
| §11 Holographic hygiene (подробно) | short trigger → §11; protocol → SOUL.md + skill |

## Guardrail: запрет рестарта при незавершённых изменениях

**Контекст:** 01.05.2026 агент выполнял аудит, в середине задачи сделал `/restart` шлюза, потеряв контекст и оставив незавершённые изменения. Из логов: `session_reset → Stopping gateway for restart` — агент сам инициировал рестарт, а не краш.

**Правило:**

1. **Запрещён `/restart` шлюза или `/reset` сессии**, пока есть незавершённые изменения — любых, не только MEMORY/USER/SOUL. Файлы, fact_store, memory, cron, config — всё считается.
2. **Вместо рестарта:** агент пишет в чат отчёт о завершённых шагах и говорит: *«Осталось сделать рестарт — подтверди»*. Рестарт происходит только после явного подтверждения пользователя.
3. **Исключение:** внешний краш (сигнал ОС, OOM, провайдер-таймаут) — агент не контролирует. Guardrail покрывает только добровольный `/restart` или `/reset`.
4. **Как определить «незавершённые изменения»:** если в текущей сессии агент уже вызвал любой write-инструмент (`memory()`, `patch()`, `write_file()`, `fact_store()` add/update/remove, `skill_manage()`, `cronjob()` create/update) — изменения считаются незавершёнными, пока агент не сообщит о завершении всех шагов и не получит подтверждение пользователя на рестарт.
5. **Реализация:** правило добавляется в MEMORY.md, SOUL.md Permission model, и docs/runbooks.md.

### Добавления в файлы

**MEMORY.md** — расширить §DO-NOT-EDIT:
```
§ DO-NOT-EDIT: MEMORY.md, USER.md, SOUL.md — не править без явного разрешения; при запросе — показывать diff. Запрещён /restart или /reset при незавершённых изменениях любого рода — сначала завершить все шаги, потом запросить подтверждение на рестарт.
```

**SOUL.md** — добавить в Permission model:
```
Запрещён /restart или /reset при незавершённых изменениях (файлы, memory, fact_store, cron, config). Сначала завершить все шаги, затем запросить подтверждение пользователя. Внешний краш — исключение.
```

**docs/runbooks.md** — добавить pitfall:
```
### Pitfall: рестарт при незавершённых изменениях
Агент не должен вызывать /restart или /reset, пока в текущей сессии есть незавершённые write-операции (файлы, memory, fact_store, cron, config). Вместо рестарта — отчёт о сделанном и запрос подтверждения.
```

## Критерии валидации

- [ ] Новый MEMORY < 1500 символов
- [ ] Нет фактов, которые уже есть в fact_store с helpful_count > 0 (кроме short triggers)
- [ ] Нет процедур, которые уже есть в skills/runbooks (кроме short triggers)
- [ ] Каждый пункт — always-on guardrail или указатель, а не on-demand факт
- [ ] Все жёсткие ограничения пользователя (Gmail, секреты, DO-NOT-EDIT) представлены
- [ ] Guardrail «no restart during mutations» добавлен в MEMORY, runbooks, SOUL