# tutu-search-flights — навигатор

## Сейчас есть

- исследование живого Tutu MCP: [`docs/mcp-notes.md`](docs/mcp-notes.md);
- записанные ответы MCP и manifest: [`fixtures/`](fixtures/);
- probe для исследования и обновления записей: [`probe.py`](probe.py);
- первоначальная product specification: [`specs/01-product.md`](specs/01-product.md);
- первая executable spec (RED): [`specs/02-successful-search.md`](specs/02-successful-search.md),
  `tests/test_successful_search.py`;
- проверки целостности research и fixtures: `tests/test_harness.py`;
- правила разработки: [`PROJECT_RULES.md`](PROJECT_RULES.md).

Рабочей реализации поиска пока нет. `SKILL.md` намеренно disabled — агент не должен выбирать этот skill.

## Следующий этап

1. Подключить тестовую привязку `tests/product_driver.py` к минимальной реализации поиска.
2. Получить GREEN первой спецификации, сохранив проверки её наблюдаемого результата.
3. Затем расширять поведение следующими executable specs.

## Текущие команды

- `make check` — все текущие проверки;
- `make test` — тесты целостности research/fixtures и продуктовые specs;
- `make spec` — первый сценарий успешного поиска; ожидается RED, пока реализации нет;
- `make lint` — Ruff;
- `make check-doc-commands` — сверка команд документации с Makefile;
- `make discover` — обновление исследования через probe; обращается к живому Tutu MCP;
- `make clean` — удаление локальных кэшей.
