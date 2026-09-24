# Записанные ответы Tutu MCP

Снято 24 сентября 2026 с `https://mcp.tutu.ru/mcp`, сервер версии 0.57.0.
Пересъёмка: `python3 probe.py meta && python3 probe.py avia`.

Живая сеть разрешена только `probe.py`. Всё остальное — спеки, тесты, разработка —
читает отсюда.

## Конверт

Фикстура никогда не голый ответ:

```json
{
  "recorded_at": "2026-09-14T…",
  "source": "tutu",
  "method": "tools/call",
  "tool": "search_avia",
  "arguments": { "origin": "Москва", "destination": "Сочи", "departure_date": "2026-10-15" },
  "note": "зачем этот файл существует",
  "volatile": ["offers[].price", "offers[].checkout_ref", "meta.search_id"],
  "response": { "envelope": …, "payload": … }
}
```

- **`recorded_at`** — опорное «сегодня» при воспроизведении. Без него записанные
  будущие рейсы через месяц станут прошедшими, отбор начнёт их выбрасывать, и набор
  покраснеет сам, обвиняя в этом код.
- **`volatile`** — поля, которые протухают. Годятся, чтобы проверить разбор формы,
  и никогда не проверяются на работоспособность. Цены и `checkout_ref` меняются
  ежедневно.
- **`response.envelope`** — кадр JSON-RPC как пришёл. **`response.payload`** — JSON,
  который Туту прячет строкой внутри текстового блока, развёрнутый для чтения.
  Хранятся оба: конверт — то, что клиент обязан пережить, нагрузка — то, что читают
  тесты.

`manifest.json` связывает файл с породившим его запросом.

## Самоописание сервера

| Файл | Что доказывает |
|---|---|
| `meta/initialize.json` | ответ `initialize`: protocol `2025-06-18`, server `0.57.0`, блок `instructions` на 23 581 символ |
| `meta/tools-list.json` | 17 инструментов с `inputSchema` — фактическая спецификация входа; `search_avia` содержит 18 параметров |
| `meta/avia-instructions.json` | текущий авиа-плейбук (16 072 символа), включая обновлённое описание deeplink |
| `meta/resource-help.json` | общая справка |
| `meta/resource-status.json` | доступность апстримов: `ok` / `reachable` / `unhealthy` / `degraded` |
| `meta/resource-geo.json` | справочник городов — вместо своего хардкода |

## Пробы `search_avia`

| Файл | Что доказывает |
|---|---|
| `avia/baseline.json` | базовая форма: 13 полей оффера, которые есть всегда |
| `avia/view-full.json` | `view: "full"` не добавляет для авиа ни одного поля — не платить за него |
| `avia/direct-only.json` | `post_filter_dropped_not_direct: 2` — сервер сам отдаёт свидетельство отбора |
| `avia/round-trip.json` | `legs` с метками `outbound` / `return`, `return_departure_at` в `checkout_ref` |
| `avia/party-2a-1c.json` | цена за всю группу: тот же рейс 5 863 ₽ за одного и 14 705 ₽ за троих |
| `avia/connections.json` | три часовых пояса и смена суток в одном предложении |
| `avia/overnight.json` | выдача, отсортированная по длительности |
| `avia/page-2.json` | `has_more`, `total_matched`, `total_matched_exact` |
| `avia/iata-airport.json` | `SVO` сузился до аэропорта, `AER` — нет; `post_filter_dropped_wrong_airport: 10` |
| `avia/empty-route.json` | отказ с подсказкой альтернативы, текстом, при коде 200 |
| `avia/past-date.json` | пусто с объяснением в `upstream_note` |
| `avia/bad-input.json` | ошибка валидации pydantic целиком в тексте |
| `avia/unknown-carrier.json` | пусто, но `post_filter_dropped_wrong_carrier: 22` — отсёк фильтр, а не источник |

Четыре последних — половина ценности набора. Они держат разбор отказов, который
иначе не проверен ничем.

## Чего здесь нет

Запись руками не правится. Изменилось поведение сервера — пересняли целиком и
разобрали разницу. Отредактированная запись перестаёт быть свидетельством и
становится мнением о том, что сервер должен был ответить.
