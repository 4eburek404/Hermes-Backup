# Plan: knowledge CLI + companion skill symbiosis

## Goal
Улучшить связку `[legacy CLI path removed; current source is the development repo skills tree]/knowledge` и companion skill `/home/konstantin/.codex/skills/knowledge-cli/SKILL.md`, чтобы skill не просто перечислял команды, а задавал decision protocol, а CLI умел машинно проверять/показывать этот контракт.

## Context
CLI уже установлен как `knowledge` и работает read-only. Companion skill есть в Codex skill store. Сейчас симбиоз слабый: skill ссылается на CLI, но CLI не знает о companion contract, не умеет проверять presence/drift companion skill и не даёт агенту self-describing подсказку.

## Non-goals
- Не трогать Docker/guest Hermes.
- Не менять `USER.md`, `MEMORY.md`, `SOUL.md`.
- Не добавлять write/fix/clean команды в CLI.
- Не делать live model calls без явного флага.

## Steps
- [x] Проанализировать текущий CLI, tests и companion skill.
- [x] Добавить failing tests на CLI-команду/метрики симбиоза.
- [x] Реализовать read-only `skill companion`/contract surface в CLI.
- [x] Обновить companion skill так, чтобы он использовал новый CLI surface.
- [x] Запустить tests и smoke checks.

## Verification
- `make test` в `[legacy CLI path removed; current source is the development repo skills tree]/knowledge` проходит.
- `knowledge --json skill companion` возвращает ok и данные о companion skill.
- `knowledge skill companion --format md` даёт компактный протокол для агента.
- Companion skill упоминает новую команду и остаётся валидным SKILL.md.

## Risks / pitfalls
- Не превратить CLI в мутационный инструмент.
- Не выводить содержимое памяти/секретов.
- Не привязать CLI только к одному skill store без override.
- Не переоценивать CLI output как permission на изменения.

## Status
Current status: done

## Notes
Создан в рамках запроса: «Анализируй релевантный skill, затем оптимизируйте и улучшайте их симбиоз (skill + cli)».

Result: добавлена CLI-команда `knowledge --json skill companion`, companion skill обновлён, tests/smoke пройдены.
