# Plans Governance

Назначение: `/home/konstantin/docs/plans/` — рабочий контур управления многошаговыми задачами Hermes/AI-агентов. План фиксирует цель, границы, шаги, проверки и статус до того, как работа расползётся по чату.

Ключевое правило Константина: **что не записано в план — скорее всего не будет сделано**.

## Source-of-truth policy

- Root `plans/` содержит только этот `README.md` и активные планы со статусом `planned`, `in_progress` или `blocked`.
- Закрытые планы переносятся в `archive/<year>/<done|cancelled|superseded>/`.
- Планы — control surface и audit trail, не долговременная база знаний.
- Durable результаты после закрытия нужно перенести в правильный слой:
  - `../infrastructure.md` — текущие факты системы, cron, models, paths, recovery;
  - `../runbooks.md` — короткие повторяемые процедуры;
  - Hermes skills — исполняемые workflows;
  - holographic `fact_store` — короткие durable facts / retrieval hooks;
  - `session_search` — подробная история, сырые логи, временный прогресс.

## Когда создавать план

Создавать отдельный `.md`-план, если задача:

- состоит из нескольких шагов;
- затрагивает docs, plans, skills, memory, cron, config, credentials metadata, код или внешние сервисы;
- может иметь побочные эффекты;
- требует анализа вариантов/trade-offs;
- может продолжаться больше одной короткой итерации;
- важна настолько, что её нельзя держать только в чате.

Простые одношаговые действия — прочитать файл, проверить статус, ответить на короткий вопрос — отдельного плана не требуют.

## Именование

Новые активные планы:

```text
YYYY-MM-DD-short-topic.md
```

Требования:

- lowercase kebab-case;
- дата — день создания плана;
- topic короткий, но различимый;
- без `final`, `new`, `temp`, `copy`;
- если план стал superseded, не переименовывать файл — сменить статус и перенести в archive.

## Статусы

Первая строка секции `## Status` должна быть машинно-читаемой:

```markdown
## Status
Current status: in_progress
```

Разрешённые статусы:

- `planned` — план создан, выполнение ещё не начато; root.
- `in_progress` — выполняется сейчас; root.
- `blocked` — нужен внешний input/решение; root.
- `done` — цель достигнута и verification пройдена; `archive/<year>/done/`.
- `cancelled` — прекращён без результата; `archive/<year>/cancelled/`.
- `superseded` — заменён другим планом/подходом; `archive/<year>/superseded/`.

## Минимальный шаблон

```markdown
# Plan: <название>

## Goal
Что должно быть достигнуто.

## Context
Почему задача нужна, ограничения, ссылки на релевантные файлы.

## Non-goals
Что специально не делаем, чтобы scope не расползся.

## Steps
- [ ] Шаг 1
- [ ] Шаг 2
- [ ] Шаг 3

## Verification
Как понять, что задача действительно выполнена.

## Risks / pitfalls
Что может пойти не так.

## Status
Current status: planned

## Notes
Короткие устойчивые заметки по ходу выполнения. Не превращать в полный лог.
```

## Lifecycle checklist

### Before work

- Проверить, нет ли уже активного релевантного плана.
- Если нет — создать план в root `plans/`.
- Указать `Goal`, `Context`, `Non-goals`, `Steps`, `Verification`, `Risks / pitfalls`, `Status`.

### During work

- Отмечать выполненные чекбоксы.
- Если задача изменилась — обновить план, а не держать новую реальность только в чате.
- Если появляется новый scope — добавить его явно в `Steps` или создать отдельный план.
- Не вставлять сырые логи; писать короткий вывод и путь к источнику, если нужен.

### Closing

Перед финальным ответом:

1. Проверить `Verification`.
2. Отметить выполненные relevant steps или явно объяснить skipped.
3. Перенести durable выводы в docs/skills/fact_store, если они не должны остаться только в плане.
4. Установить `Current status: done|cancelled|superseded`.
5. Добавить короткий итог в `Notes`.
6. Перенести файл в `archive/<year>/<status>/`.

## Что не должно жить в планах

- Секреты, токены, пароли, private keys, полные credential JSON.
- Полные terminal logs, raw model outputs, transcript dumps.
- Устойчивые операционные факты, которые должны быть в `infrastructure.md`.
- Повторяемые процедуры, которые должны быть в `runbooks.md` или skill.
- Пользовательские предпочтения, которые должны быть в `user-context.md`, built-in memory или holographic.
- “Когда-нибудь надо бы” без конкретной цели/verification.

## Периодическая гигиена

Для review `plans/`:

1. Составить inventory root + archive: файлы, статусы, unchecked steps.
2. В root оставить только `README.md` и планы со статусами `planned|in_progress|blocked`.
3. Done/cancelled/superseded перенести в archive.
4. Найти планы без `Current status:` и нормализовать при следующем касании.
5. Проверить secret-risk regex по markdown.
6. Проверить, не остался ли durable result только в архивном плане.

## Anti-patterns

- Root забит закрытыми планами, и непонятно, что активно.
- План без `Verification` или `Current status:`.
- Один план на несколько независимых задач.
- План используется как лог всего разговора.
- Завершённый план содержит единственную копию важного operational fact.
- Superseded план выглядит как актуальная инструкция.
- Архив чистится удалением без причины.
