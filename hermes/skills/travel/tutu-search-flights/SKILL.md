---
name: tutu-search-flights
description: "Ищет авиабилеты через Tutu MCP SDK и сообщает только подтверждённые источником факты."
version: "0.1.0"
metadata:
  hermes:
    category: travel
    tags: [travel, flights, tutu, mcp]
---

# Поиск авиабилетов Tutu

Для живого поиска запускай `tutu_search_flights.py` из каталога этого skill, передавая
один JSON-объект с аргументами `search_avia`:

`uv run python tutu_search_flights.py '<JSON>'`

Скрипт подключается к `https://mcp.tutu.ru/mcp` через MCP Python SDK и вызывает
`search_avia`. Не используй native Hermes Tutu MCP tool, `probe.py`, HTTP/curl или
другой transport как production-путь.

Не меняй запрошенные маршрут, даты или состав пассажиров без необходимости.

Для предложения с несколькими сегментами или для round-trip используй `legs` и
`legs[].segments`; не представляй такое предложение как один прямой рейс.

Если `offers` пуст:
- перед выводом проверь `upstream_note`, `post_filter_dropped` и
  `total_matched_exact`;
- не утверждай «рейсов нет», если источник дал объяснение, фильтр отбросил
  предложения или полнота совпадений не подтверждена.

Сообщай только предложения, цены, тарифы и условия, которые присутствуют в результате
поиска. Не додумывай неизвестные значения и не выполняй альтернативные поиски без причины.
