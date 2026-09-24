# tutu-search-flights — навигатор

## Сейчас есть

- исследование живого Tutu MCP: [`docs/mcp-notes.md`](docs/mcp-notes.md);
- записанные ответы MCP и manifest: [`fixtures/`](fixtures/);
- probe для исследования и обновления записей: [`probe.py`](probe.py);
- первоначальная product specification: [`specs/01-product.md`](specs/01-product.md);
- первая executable spec и её реализация: [`specs/02-successful-search.md`](specs/02-successful-search.md),
  `tests/test_successful_search.py`, `tutu_search_flights.py`;
- agent specification живого поиска: [`specs/agent/01-live-search.md`](specs/agent/01-live-search.md);
- проверки целостности research и fixtures: `tests/test_harness.py`;
- правила разработки: [`PROJECT_RULES.md`](PROJECT_RULES.md).

Живой production-путь выполняется через MCP Python SDK 2.2.0; `probe.py` остаётся только research-инструментом.

## Следующий этап

1. Проверить `make live` в окружении с доступом к `https://mcp.tutu.ru/mcp`.
2. Прогнать agent specification через общий evaluate harness.
3. Затем расширять поведение следующими executable specs.

## Текущие команды

- `make check` — все текущие проверки;
- `make test` — тесты целостности research/fixtures и продуктовые specs;
- `make spec` — детерминированный сценарий успешного поиска;
- `make live` — opt-in живой поиск через MCP SDK;
- `make lint` — Ruff;
- `make check-doc-commands` — сверка команд документации с Makefile;
- `make discover` — обновление исследования через probe; обращается к живому Tutu MCP;
- `make clean` — удаление локальных кэшей.
