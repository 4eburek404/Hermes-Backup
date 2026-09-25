# tutu-search-flights — навигатор

## Сейчас есть

- исследование живого Tutu MCP: [`docs/mcp-notes.md`](docs/mcp-notes.md);
- записанные raw MCP responses и manifest: [`fixtures/`](fixtures/);
- research probe для обновления записей: [`probe.py`](probe.py);
- product specification: [`specs/01-product.md`](specs/01-product.md);
- S1 — сохранение успешного ответа: [`specs/02-successful-search.md`](specs/02-successful-search.md);
- S2 — production CLI → MCP SDK → `search_avia`: [`specs/03-production-sdk-search.md`](specs/03-production-sdk-search.md);
- S3 — tool-level error не является пустой выдачей: [`specs/04-tool-error.md`](specs/04-tool-error.md);
- S4 — party_total и состав пассажиров: [`specs/05-party-pricing.md`](specs/05-party-pricing.md);
- S5 — пересадочные segments: [`specs/06-connections.md`](specs/06-connections.md);
- S6 — round-trip: [`specs/07-round-trip.md`](specs/07-round-trip.md);
- S7 — объяснение пустой выдачи: [`specs/08-empty-result-evidence.md`](specs/08-empty-result-evidence.md);
- S8 — ошибки production CLI: [`specs/09-cli-errors.md`](specs/09-cli-errors.md);
- opt-in live smoke test реального Tutu MCP: `tests/test_live_search.py`;
- правила разработки: [`PROJECT_RULES.md`](PROJECT_RULES.md).

Production-путь живого поиска реализован через MCP Python SDK 2.2.0.
`probe.py` не является production transport.

## Проверка текущего объёма

Матрица [docs/verification.md](docs/verification.md) связывает S1–S8 с test node IDs,
описывает фактический охват и отделяет подтверждённое от отложенного. Она не заменяет
запуск команд и не утверждает общий GREEN без результата проверки.

- `make spec` — детерминированные product и CLI specs без сети;
- `make check` — локальный набор тестов, lint и проверка команд в документации;
- `make live` — opt-in живой поиск через MCP SDK;
- `make discover` — обновление research fixtures через `probe.py`;
- `make clean` — удаление локальных кэшей.

Статус внешней CI и agent evaluation фиксируется отдельно. Локальная подготовка
workflow не подтверждает remote GREEN или branch protection. Agent evaluation
остаётся отдельным внешним шагом, не заменяющим product specs, gates или live smoke.
