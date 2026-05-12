# Plan: knowledge CLI P0 refactor

## Goal
Исправить P0 correctness defects в bundled `knowledge` CLI и companion skill без изменения protected core files (`USER.md`, `MEMORY.md`, `SOUL.md`).

## Context
Пользователь одобрил выполнение после read-only аудита `knowledge-architecture`. Проверенный source tree: `/home/konstantin/.hermes/hermes-agent`, branch `fix/ollama-native-auxiliary-routing`, HEAD `6ac6367f196e`. Рабочее дерево уже содержит чужие/предыдущие dirty изменения; патчи должны быть scoped и не перетирать WIP.

## Non-goals
- Не переписывать весь `SKILL.md` в этом проходе.
- Не редактировать `USER.md`, `MEMORY.md`, `SOUL.md`.
- Не запускать live model/API distillation.
- Не раскрывать secret-risk содержимое; только counts/classes.
- Не делать commit/push без отдельного явного запроса.

## Steps
- [x] Проверить branch/HEAD/status и target diffs.
- [x] Добавить regression tests для worker path, SOUL path, folded YAML description, report scope / docs audit aggregation.
- [x] Убедиться, что новые regression tests падают на текущем коде.
- [x] Исправить CLI defaults/path detection/read-only SQLite/frontmatter/report scope.
- [x] Обновить CLI README dependency wording.
- [x] Исправить stale path в Codex companion skill.
- [x] Убрать generated `__pycache__` из skill tree.
- [x] Запустить focused tests, AST syntax, `knowledge --json doctor`, `knowledge --json report --all`, `audit_skill.py`.
- [x] Проверить diff и описать remaining baseline issues.

## Verification
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` — passed, 11 tests OK.
- AST parse of changed Python files — passed.
- `knowledge --json doctor` — passed, version `0.1.0`.
- `knowledge --json report --all` — passed; docs findings included.
- `python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill knowledge-architecture --json` — passed with existing warnings only (`missing_section`, `skill_large`).
- `git diff --check` — passed.
- No `__pycache__` / `.pyc` left under `skills/note-taking/knowledge-architecture/cli/`.

## Risks / pitfalls
- Existing dirty files may belong to prior WIP; unrelated edits were not overwritten.
- Secret scan findings were reported only as counts/classes; values were not printed.
- Tests can create bytecode unless `PYTHONDONTWRITEBYTECODE=1` is set; generated artifacts were removed after checks.
- CLI remains read-only; evidence collection is not permission to mutate protected files.

## Status
Current status: done

## Notes
Closed after P0 fixes and verification. Durable maintenance lessons were promoted to the `knowledge-architecture` skill reference `references/knowledge-cli-maintenance.md`; this plan is audit trail only.
