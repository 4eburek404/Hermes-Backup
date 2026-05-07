# Plan: Travelpayouts flight-search plugin for Hermes

## Goal

Внедрить в Hermes Agent plugin для поиска авиабилетов через Travelpayouts API, портировав **все фичи** из Telegram-бота (`bot/modules/flights/`) и WebApp (`webapp/src/`), за исключением Ui-специфичных компонентов (aiogram-dialog окна, React-компоненты).

## Context

### Источники (что портируем)

**Бот: `/home/konstantin/bot/bot/modules/flights/`**

| Файл | Фичи |
|---|---|
| `models.py` | Pydantic: `City`, `Airport`, `Airline`, `Plane`, `FlightLeg`, `Transfer`, `FlightSegment`, `FlightPrice`, `SearchParams` |
| `api.py` | `TravelpayoutsClient`: GraphQL поиск + REST Data API (cities/airports/airlines справочники, `require_auth=False`); singleton; `RateLimitError`, `TravelpayoutsAPIError` |
| `api_schemas.py` | Enriched DTO: `CityResult`, `CitiesResponse`, `FlightSearchRequest`, `LegOut`, `TransferOut`, `SegmentOut`, `FlightOut`, `FlightsResponse`, `ErrorDetail`, `ErrorResponse` |
| `web_handlers.py` | `_duration_min()`, `_resolve_airport_name()`, `_build_segment()`, `_build_booking_url()` (ticket_link + marker), `_flight_to_out()` (обогащение через кэши); REST endpoints: `/api/cities`, `/api/flights`, `/api/templates`; `format_time()`, `format_date()` |
| `formatters.py` | `format_time()`, `format_date()`, `format_duration()`, `format_transfer()`, `format_flight_leg()`, `format_segment()`, `format_results()` (HTML с пагинацией), `_build_aviasales_url()`, `build_aviasales_link()` |
| `keyboards.py` | `POPULAR_ROUTES`: 4 пресета (SVX→MOW, SVX→LED, SVX→AER, SVX→IST) |
| `parsers.py` | `parse_graphql_flight()`, `flight_dedup_key()`, `parse_segment()` |
| `queries.py` | `GRAPHQL_ONE_WAY_QUERY`, `GRAPHQL_ROUND_TRIP_QUERY` |
| `cache/base.py` | `BaseCache`: async `ensure_loaded()`, TTL 7 дней, файловая персистентность (`~/.cache/bot/`), asyncio lock, `_fetch_data()` abstract |
| `cache/airlines.py` | `AirlinesCache(BaseCache)`: `get_name(code)` — ищет `name_translations["ru"]` → `name` |
| `cache/airports.py` | `AirportsCache(BaseCache)`: `get_by_code()`, `get_by_city()` |
| `cache/cities.py` | `CitiesCache(BaseCache)`: `search(query, limit)` — fuzzy match по `name` + `name_translations.values()`, `get_by_code()` |
| `cache/planes.py` | `PlanesCache(BaseCache)`: `get_name(code)` |
| `cache/__init__.py` | Singleton getters: `get_airlines_cache()`, `get_airports_cache()`, `get_cities_cache()`, `get_planes_cache()` |
| `dialog_handlers.py` | `_handle_city_input()`: IATA→direct match, name→`search()`, множественные→выбор; `on_search_clicked()`: поиск + пагинация |
| `handlers.py` | `/flights` — запуск диалога; `/webapp` — открытие Mini App |
| `dialogs.py` | aiogram-dialog: FSM-состояния, календарь, popular routes (UI — **не портируем**) |
| `states.py` | `FlightSearchStates` — FSM-стейты (UI — **не портируем**) |

**WebApp: `/home/konstantin/bot/webapp/src/`**

| Файл | Фичи |
|---|---|
| `types/api.ts` | TS-зеркало `api_schemas.py`: `SortBy = 'cheapest' \| 'fastest' \| 'earliest' \| 'fewest_stops'`, `Filters { maxPrice, maxStops, departureTime }`, `RouteTemplate` |
| `store/searchStore.ts` | Client-side сортировка (`getFilteredSortedFlights`): cheapest/fastest/earliest/fewest_stops; фильтры: `maxPrice`, `maxStops`, `departureTime` (morning 6-12, afternoon 12-18, evening 18-24, night 0-6) |
| `components/Results/SortFilterSheet.tsx` | UI: чипы sort/stops/time — логика та же, что в store |
| `components/SearchForm/RouteTemplates.tsx` | UI популярных маршрутов |
| `api/flights.ts` | `searchFlights(req)` → POST `/api/flights` |
| `api/cities.ts` | `searchCities(q)` → GET `/api/cities?q=...` |
| `api/templates.ts` | `getTemplates()` → GET `/api/templates` |
| `hooks/useCitySearch.ts` | Debounce 300ms city search |

### Текущий плагин: `~/.hermes/plugins/travelpayouts-flights/`

| Файл | Что реализовано |
|---|---|
| `models.py` | `FlightLeg`, `Transfer`, `FlightSegment`, `FlightPrice` (dataclasses, `to_dict()` + `booking_url`) |
| `client.py` | `TravelpayoutsClient`: GraphQL-only, in-memory cache (5 мин TTL), rate limit guard, `build_booking_url()`, `RateLimitError`, `TravelpayoutsAPIError` |
| `tools.py` | `travelpayouts_flight_search()`: IATA-only валидация, нормализация, limit [1..20], error handling, `CACHE_NOTE` |
| `schemas.py` | Tool JSON schema: `origin`, `destination`, `departure_date`, `return_date`, `direct_only`, `currency`, `limit` |
| `parsers.py` | `parse_graphql_flight()`, `flight_dedup_key()`, `parse_segment()` |
| `queries.py` | `GRAPHQL_ONE_WAY_QUERY`, `GRAPHQL_ROUND_TRIP_QUERY` |
| `plugin.yaml` | `kind: standalone`, `provides_tools: [travelpayouts_flight_search]`, `requires_env: [TRAVELPAYOUTS_TOKEN]` |

### Gap-анализ: чего нет в плагине

1. **Справочники и обогащение** — нет `cache/` (BaseCache + Airlines/Airports/Cities/Planes), нет Data API REST, нет Pydantic моделей справочников
2. **Обогащённый вывод** — нет `api_schemas.py` DTO (`LegOut`, `TransferOut`, `SegmentOut`, `FlightOut`), нет pipeline enrichment
3. **Поиск по названию города** — нет `CitiesCache.search()`, нет резолва название→IATA
4. **Партнёрские ссылки** — `build_booking_url()` есть, но без `build_aviasales_link()` fallback (конструирование URL из IATA+дат при пустом `ticket_link`)
5. **Популярные маршруты** — нет `POPULAR_ROUTES`
6. **Сортировка** — нет `sort_by` (cheapest/fastest/earliest/fewest_stops)
7. **Фильтрация** — нет `max_price`, `max_stops`, `departure_time` (morning/afternoon/evening/night)
8. **Форматирование** — нет `formatters.py` (время, дата, длительность, сегменты, пересадки, HTML-результаты)
9. **Гибкость дат** — нет `flexibility` (±N дней)
10. **Информация о пересадках** — нет enriched `TransferOut` (airport_name, visa_required, night_transfer, duration_min) в tool output

## Non-goals

- Не покупать и не бронировать билеты.
- Не интегрироваться с GDS/Sabre/Amadeus.
- Не менять Travelpayouts API, Telegram bot WebApp или webapp UI.
- Не портировать aiogram-dialog FSM/окна и React-компоненты (UI-логика бота и webapp не нужна для Hermes tool).
- Не включать plugin автоматически без явного решения.
- Не логировать и не выводить Travelpayouts token/marker как секретные значения.

## Steps

### Этап 1 — базовый поиск (DONE ✓)

- [x] Зафиксировать контракт plugin tool.
- [x] Выбрать стратегию переиспользования кода (вариант A: self-contained plugin).
- [x] Создать plugin skeleton в `~/.hermes/plugins/travelpayouts-flights/`.
- [x] Настроить секреты и non-secret config.
- [x] Реализовать сетевой слой с защитами.
- [x] Реализовать нормализацию и ранжирование ответа.
- [x] Добавить защиту от resource abuse.
- [x] Написать тесты.
- [x] Включить и проверить вручную.
- [x] После успешной проверки обновить durable layers.

### Этап 2 — справочники, обогащение и поиск по названию (DONE ✓)

**Решения:** Pydantic для моделей справочников (1A), поддиректория `cache/` (2A), ленивая загрузка (3A), отдельный `schemas_enriched.py` (4A).

**2a. Data API и кэш-подсистема**

- [x] Перенести Pydantic модели справочников из `models.py`: `City`, `Airport`, `Airline`, `Plane`
- [x] Адаптировать `cache/base.py` → plugin:
  - Убрать `bot.core.config` → `os.getenv` / plugin dir для путей
  - Убрать `bot.shared.http_session` → `aiohttp` напрямую
  - Путь персистентности: `~/.hermes/plugins/travelpayouts-flights/cache/`
  - Формат: JSON файлы (как в боте)
- [x] Перенести и адаптировать `cache/airlines.py`: `AirlinesCache.get_name(code, lang="ru")`
- [x] Перенести и адаптировать `cache/airports.py`: `AirportsCache.get_by_code()`, `get_by_city()`
- [x] Перенести и адаптировать `cache/cities.py`: `CitiesCache.search(query, limit)`, `get_by_code()`
- [x] Перенести и адаптировать `cache/planes.py`: `PlanesCache.get_name(code)`
- [x] Перенести singleton getters: `get_airlines_cache()`, `get_airports_cache()`, `get_cities_cache()`, `get_planes_cache()`
- [x] Расширить `client.py`: добавить Data API REST методы (`get_cities()`, `get_airports()`, `get_airlines()`, `get_planes()`) с `require_auth=False`
- [x] Обновить `plugin.yaml`: добавить `TRAVELPAYOUTS_MARKER` в `requires_env` (опциональный, для партнёрских ссылок)

**2b. Enriched DTO и pipeline**

- [x] Создать `schemas_enriched.py` (или расширить `schemas.py`):перенести из `api_schemas.py`:
  - `CityResult`, `CitiesResponse`
  - `LegOut`, `TransferOut`, `SegmentOut`, `FlightOut`, `FlightsResponse`
  - `ErrorDetail`, `ErrorResponse`
- [x] Перенести pipeline enrichment из `web_handlers.py`:
  - `_duration_min(dep, arr)` → утилита
  - `_resolve_airport_name(code, airports_cache, cities_cache)` → `airport_code → Airport → city_code → City → "Город (КОД)"`
  - `_build_segment(seg, caches)` → `SegmentOut` с названиями авиакомпаний, аэропортов, самолётов
  - `_flight_to_out(flight, currency, caches)` → `FlightOut` с полным обогащением

**2c. Поиск по названию города**

- [x] Добавить резолв ciudad в `tools.py`:
  - Если `origin`/`destination` не IATA-код (3 буквы) — искать через `CitiesCache.search()`
  - При единственном совпадении — автоматически подставить IATA
  - При множественных совпадениях — вернуть список для уточнения пользователем
- [x] Обновить tool schema: `origin`/`destination` могут быть названием города

### Этап 3 — форматирование и UX (DONE ✓)

**Решение:** форматирование (бывший этап 5) вынесено перед партнёрскими ссылками, сортировкой и фильтрацией — пользователь должен видеть человекочитаемый вывод ASAP.

- [x] Перенести форматтеры из `formatters.py`:
  - `format_time(iso_time)`, `format_date(iso_time)`, `format_date_full(iso_time)`, `format_duration(dep, arr)`
  - `format_transfer(transfer)` — пересадки с emoji (🌙 ночная, ⚠️ виза)
  - `format_flight_leg(leg, airlines)`, `format_segment(segment, airlines)`
- [x] Обогащённый вывод в tool response: добавить `airline_name`, `origin_name`, `destination_name`, `carrier_name`, `aircraft_name`, `duration_min` в каждый `FlightPrice.to_dict()`
- [x] По умолчанию `direct_only=false` (сейчас `false` — ОК), но при отсутствии прямых — добавить подсказку «прямых нет, показаны с пересадками»
- [x] Всегда упоминать, что цены из кэша, не гарантированы (`CACHE_NOTE` — уже есть)

### Этап 4 — партнёрские ссылки и популярные маршруты

- [x] Перенести `_build_aviasales_url(origin, dest, depart_date, return_date)` из `formatters.py` — fallback при пустом `ticket_link`
- [x] Интегрировать с `_build_booking_url()` из `web_handlers.py`: если `ticket_link` → нормализовать + marker; иначе → Aviasales link
- [ ] Перенести `POPULAR_ROUTES` из `keyboards.py` (4 пресета SVX→MOW/LED/AER/IST)
- [ ] Добавить tool `travelpayouts_popular_routes` или включить маршруты в ответ `flight_search`

### Этап 5 — сортировка и фильтрация

**5a. Сортировка**

- [ ] Добавить параметр `sort_by` в tool schema: `cheapest` (default) | `fastest` | `earliest` | `fewest_stops`
- [ ] Реализовать server-side сортировку в `tools.py` (как в `searchStore.ts: getFilteredSortedFlights`):
  - `cheapest`: сортировка по `price` (уже есть default)
  - `fastest`: сортировка по `duration_min` (вычисленный из outbound segment)
  - `earliest`: сортировка по `departure_at`
  - `fewest_stops`: сортировка по `transfers`, затем `price`

**5b. Фильтрация**

- [ ] Добавить параметры фильтрации в tool schema:
  - `max_price: int | None` — отсечь рейсы дороже
  - `max_stops: int | None` — ограничить пересадки (0=прямой, 1, 2+)
  - `departure_time: list[str] | None` — время суток: `morning` (6-12), `afternoon` (12-18), `evening` (18-24), `night` (0-6)
- [ ] Реализовать server-side фильтрацию в `tools.py` (как в webapp store)

### Этап 6 — гибкость дат и расширенная информация

- [ ] Добавить параметр `flexibility: int = 0` (0-7 дней) в tool schema и `SearchParams`
- [ ] При `flexibility > 0`: запросить несколько дат в GraphQL (`depart_dates: [D-1, D, D+1, ...]`)
- [ ] Добавить enriched `TransferOut` в tool output:
  - `airport_name` (через `_resolve_airport_name`)
  - `country_code`, `duration_min`, `night_transfer`, `visa_required`
  - Из `_build_segment()` — уже переносится на этапе 2b
- [ ] Добавить `trip_duration_days` в выходной `FlightOut`

### Этап 7 — тесты и верификация

- [ ] Обновить тесты: mock Data API responses для справочников
- [ ] Тест обогащения: проверить `airline_name="Уральские авиалинии"` для U6
- [ ] Тест поиска по названию: `"Екатеринбург"` → `SVX`; множественные → список
- [ ] Тест сортировки: `sort_by=fastest` → порядок по `duration_min`
- [ ] Тест фильтрации: `max_price=10000` отсекает дороже; `departure_time=morning` фильтрует 6-12
- [ ] Тест партнёрских ссылок: с marker и без; fallback Aviasales URL
- [ ] Тест гибкости дат: `flexibility=1` → 3 даты в запросе
- [ ] Smoke-тест: поиск «Екатеринбург → Москва» по названию + русские названия в выводе

## Verification

### Этап 1 (пройден ✓)

- [x] `hermes plugins list` показывает `travelpayouts-flights` enabled.
- [x] Tool выполняет smoke search SVX→MOW.
- [x] Секреты не утекают.

### Этап 2

- [x] `CitiesCache.search("Екатеринбург")` возвращает город с `code="SVX"`.
- [x] `AirlinesCache.get_name("U6")` возвращает `"Уральские авиалинии"`.
- [x] `AirportsCache.get_by_code("DME")` возвращает аэропорт с русским названием.
- [x] Tool output JSON содержит `airline_name`, `origin_name`, `destination_name`, `aircraft_name`, `duration_min`.
- [x] Поиск `origin="Екатеринбург"` автоматически резолвится в `SVX`.
- [x] Справочник обновляется из Data API при первом запуске и при истечении TTL.
- [x] Тесты новых кэшей и обогащения проходят.

### Этап 3 (форматирование) (пройден ✓)

- [x] Tool output содержит человекочитаемые названия городов/аэропортов/авиакомпаний.
- [x] Пересадки содержат `night_transfer`, `visa_required`, `duration_min` и `formatted` string с emoji.
- [x] При отсутствии прямых рейсов есть подсказка (`direct_not_available` + warning).
- [x] Верхнеуровневый `formatted` HTML-блок с полным форматированием рейсов.
- [x] Предформатированные поля рядом с ISO: `departure_formatted`, `arrival_formatted`, `duration_formatted`, `price_formatted`, `transfers_formatted`.

### Этап 4

- [x] При пустом `ticket_link` генерируется Aviasales fallback URL с `marker`.
- [x] При непустом `ticket_link` URL содержит `marker` параметр.
- [ ] `POPULAR_ROUTES` доступны через tool или в ответе.

### Этап 5

- [ ] `sort_by=fastest` возвращает рейсы, отсортированные по `duration_min`.
- [ ] `max_price=10000` отсекает рейсы дороже 10K.
- [ ] `departure_time=morning` фильтрует рейсы с вылетом 06:00–12:00.
- [ ] `max_stops=0` показывает только прямые рейсы.

### Этап 6

- [ ] `flexibility=1` расширяет поиск на ±1 день.
- [ ] `trip_duration_days` присутствует в выходных данных.

### Этап 7

- [ ] Все тесты проходят.
- [ ] Smoke-тест «Екатеринбург → Москва» даёт полноценный enriched output.

## Risks / pitfalls

- **Секреты:** Travelpayouts token передавать через header `X-Access-Token`, не URL param. Marker — не секрет, но не печатать.
- **Bot coupling:** не импортировать `bot.*` напрямую — только адаптировать код (копировать с адаптацией).
- **Data API format:** Travelpayouts Data API может менять формат; нужен мягкий парсинг с fallthrough (try/except в конструкторах Pydantic).
- **TTL кэша:** 7 дней для справочников, но при первом запуске нужен network запрос до ответа на поиск — ленивая загрузка, не блокировать tool init.
- **Race condition:** два одновременных поиска → параллельная загрузка справочника; нужен asyncio lock (как в bot `BaseCache`).
- **Memory:** справочники в RAM; airlines ~1.5K, airports ~7K, cities ~500 — приемлемо.
- **Marker env:** `TRAVELPAYOUTS_MARKER` — опциональный env var, не обязательно для работы.
- **Ollama JSON:** если используем Ollama-модели — `json_object` + `enums` + `strip_codeblock()`, НЕ `json_schema`.
- **flexibility GraphQL:** Travelpayouts GraphQL принимает массив дат — `depart_dates: ["2026-05-01", "2026-05-02", ...]`; нужно убедиться что пагинация не отсекает соседние даты.
- **Pydantic vs dataclass:** бот использует Pydantic для моделей справочников, плагин — dataclasses для FlightPrice. Оба подхода валидны, но нужно аккуратно конвертировать при обогащении.

## Status
Current status: in_progress


## Notes
2026-05-05: active-plan audit — **не закрыт**. Проверено по live code/tests:
- `tests/run_tests.py` plugin smoke suite проходит: 4/4.
- `build_aviasales_fallback_url()` и booking URL marker работают (`https://www.aviasales.ru/search/SVX1907MOW1?marker=...`).
- Cache/enrichment этап 2 фактически реализован; устаревшие чекбоксы этапа 2 отмечены выполненными.
- Остались реальные blockers: `POPULAR_ROUTES`/popular routes tool отсутствуют; `sort_by`, `max_price`, `departure_time`, `max_stops`, `flexibility` отсутствуют в tool schema.
- `pytest tests` из корня plugin падает на collection из-за hyphenated plugin dir/relative import; canonical test runner для plugin сейчас `python3 tests/run_tests.py`.


2026-04-29: этап 1 завершён. Создан self-contained plugin с базовым поиском по IATA-кодам.

2026-04-29: полный анализ bot + webapp. Обнаружены фичи, отсутствующие в старом плане: форматтеры (formatters.py), enriched TransferOut (visa/night), гибкость дат (flexibility), Aviasales fallback URL, popular routes как отдельная фича. План переписан с 4→7 этапов с детальным gap-анализом.

2026-04-29: **этап 3 завершён.** Добавлено:
- `formatters.py`: `format_time`, `format_date`, `format_date_full`, `format_duration`, `format_transfer` (с emoji 🌙/⚠️), `format_price` (валюта с символом), `format_transfers_count`, `format_flight_results` (Telegram-HTML)
- `schemas_enriched.py`: `formatted`-поля в `LegOut` (departure/arrival), `TransferOut` (formatted string), `SegmentOut` (departure/arrival/duration formatted), `FlightOut` (transfers_formatted, duration_formatted, price_formatted, direct_not_available)
- `enrichment.py`: заполнение formatted-полей при обогащении, вызов формatters из build_segment/flight_to_out
- `tools.py`: `direct_not_available` hint, `formatted` HTML в верхнеуровневом ответе, заголовок с городами
- Тесты: 10 новых тестов в `test_formatters.py` + 4 старых, все проходят
- Smoke-тест SVX→MOW: человекочитаемый вывод корректен

Архитектурные решения этапа 3:
- Вариант 1-А: JSON + `formatted` поле — tool возвращает и структурированные данные, и готовый Telegram-HTML
- Вариант 2-А: предформатированные строки рядом с ISO (departure_formatted, duration_formatted и т.д.)
- Вариант 3-А: emoji в formatted-выводе (🌙 ночная, ⚠️ виза, 🔄 пересадка)
- Вариант 4-А: `direct_not_available: true` + текстовое hint в warnings
- Вариант 5-А: Telegram-HTML для formatted-вывода

2026-04-29: **этап 2 завершён.** Добавлено:
- `cache/` подсистема: `BaseCache` (ленивая загрузка, TTL 7 дней, файловая персистентность, asyncio lock), `AirlinesCache`, `AirportsCache`, `CitiesCache`, `PlanesCache`, singleton getters
- Pydantic модели справочников: `City`, `Airport`, `Airline`, `Plane`
- `schemas_enriched.py`: `LegOut`, `TransferOut`, `SegmentOut`, `FlightOut`, `CityResult`, `CitiesResponse`
- `enrichment.py`: `duration_min()`, `resolve_airport_name()`, `build_segment()`, `flight_to_out()`, `build_aviasales_fallback_url()`, `_resolve_booking_url()`
- `tools.py`: поиск по названию города через `_resolve_location()`, disambiguation при множественных совпадениях, обогащённый вывод через `FlightOut.model_dump()`, параллельная загрузка 4 кэшей
- `schemas.py`: tool schema обновлён — origin/destination принимают название города
- `plugin.yaml`: v0.2.0, добавлен `TRAVELPAYOUTS_MARKER`
- Smoke-тесты: все прошли