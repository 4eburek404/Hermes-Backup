# tutu-search-flights — навигатор

## Сейчас есть

- исследование живого Tutu MCP: [`docs/mcp-notes.md`](docs/mcp-notes.md);
- записанные ответы MCP и manifest: [`fixtures/`](fixtures/);
- probe для исследования и обновления записей: [`probe.py`](probe.py);
- первоначальная product specification: [`specs/01-product.md`](specs/01-product.md);
- проверки целостности research и fixtures: `tests/test_harness.py`;
- правила разработки: [`PROJECT_RULES.md`](PROJECT_RULES.md).

Рабочей реализации поиска пока нет. `SKILL.md` намеренно disabled — агент не должен выбирать этот skill.

## Следующий этап

1. Создать executable product specifications.
2. Затем реализовать минимум, необходимый для подтверждённых specs.

## Текущие команды

- `make check` — все текущие проверки;
- `make test` — тесты целостности research/fixtures;
- `make lint` — Ruff;
- `make check-doc-commands` — сверка команд документации с Makefile;
- `make discover` — обновление исследования через probe; обращается к живому Tutu MCP;
- `make clean` — удаление локальных кэшей.
