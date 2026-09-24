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
- opt-in live smoke test реального Tutu MCP: `tests/test_live_search.py`;
- правила разработки: [`PROJECT_RULES.md`](PROJECT_RULES.md).

Production-путь живого поиска реализован через MCP Python SDK 2.2.0.
`probe.py` не является production transport.

## Текущий этап

Закрыть продуктовый SDD-цикл текущего объёма:

1. `make spec` — все детерминированные executable specs должны быть GREEN.
2. `make check` — общий локальный gate должен быть GREEN.
3. `make live` — отдельно подтвердить реальную SDK-интеграцию с Tutu.
4. Только после этого формулировать следующую продуктовую спецификацию.

Agent evaluate не заменяет эти проверки и не является следующим шагом, пока
production-поведение текущего объёма не закреплено спецификациями и тестами.

## Текущие команды

- `make spec` — S1–S7 без сети;
- `make check` — тесты, lint и проверки документации;
- `make live` — opt-in живой поиск через MCP SDK;
- `make discover` — обновление research fixtures через `probe.py`;
- `make clean` — удаление локальных кэшей.
