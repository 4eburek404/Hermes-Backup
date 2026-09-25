# S2 — production-поиск через MCP SDK

Эта исполняемая спецификация защищает production CLI → MCP SDK → `search_avia`
на записанном успешном ответе Tutu.

## Дано

Есть JSON-запрос и raw ответ Tutu из `fixtures/avia/baseline.json`, а также
записанный ответ `tools/list` из `fixtures/meta/tools-list.json`.

## Когда

Production CLI получает запрос. Установленный MCP SDK 2.2.0 создаёт настоящий
`Client` и выполняет session/handshake с локальным in-memory MCP `Server`;
сервер отдаёт записанные результаты `tools/list` и `search_avia`.

## Тогда

- production передаёт `Client` адрес `https://mcp.tutu.ru/mcp`;
- вызывается `search_avia` ровно один раз с исходными аргументами;
- команда завершается с кодом 0 и пишет один JSON-результат в stdout;
- результат совпадает с продуктовыми данными S1;
- в исторической записи baseline есть три предложения, первый рейс `DP-6949`
  и первая цена `4446.87 RUB`. Это контрольные значения данной записи, а не
  требование к будущим ответам живого поиска.

## Исполняемая проверка и граница

Проверку запускает [test_production_sdk_search.py](../tests/test_production_sdk_search.py)
::`test_production_cli_uses_sdk_search_avia_and_returns_product_result`.
В ней используются MCP `Client`, session, `call_tool` и типы SDK 2.2.0; тест
перенаправляет только конструктор `mcp.Client` на сохранённый настоящий
`Client(in_memory_server)`. Handler сервера записывает имя и аргументы вызова.

Проверка детерминированная и не использует HTTP или живой Tutu. Она подтверждает
обмен внутри настоящего SDK с in-memory server и проекцию записанного ответа.
`make live` остаётся отдельной проверкой реального сетевого endpoint.
