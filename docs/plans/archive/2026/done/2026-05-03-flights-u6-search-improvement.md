# Plan: Доработка U6-поиска в flights CLI

## Goal
Улучшить `flights u6-prices` в полноценный U6 price-discovery workflow, а не оставлять только caveat «официальный сайт неполноценный».

## Context
- Created: 2026-05-03.
- Project path: `[legacy CLI path removed; current source is the development repo skills tree]/flights`.
- `flights u6-prices` использует public `mobile_calendar` endpoint без auth.
- Текущий endpoint даёт daily min prices примерно на 3 месяца от `--from-date`.
- Endpoint не даёт номера рейсов, времена вылета/прилёта или availability.
- Текущий баг: пустой ответ превращается в `no_results` с текстом «route may not exist», хотя это должно быть warning, а не утверждение об отсутствии рейсов.

## Non-goals
- Не лезем в `book.uralairlines.ru` IBE API: там требуется session/auth, это агрессивно.
- Не разбираем frontend JS и `env.json`.
- Не обходим CORS/CSRF/access control.
- Не утверждаем наличие/отсутствие рейсов только по календарю цен U6 без cross-check.

## Steps
- [x] Исправить обработку пустого ответа: no `dates` key или `dates: []` должны давать warning/empty reason, а не ложный `no_results`.
- [x] Добавить в JSON явные поля `ok` и `empty_reason`.
- [x] Не утверждать «рейсов нет» без проверки других источников.
- [x] Добавить `--sort` (`price`/`date`, default `price`).
- [x] Добавить `--limit N` с default 20.
- [x] Добавить `--date YYYY-MM-DD` для проверки конкретной даты.
- [x] Добавить `--min-price` / `--max-price` фильтры.
- [x] Добавить статистику: min/avg/max цена и количество priced dates.
- [x] Улучшить human output: топ-5 дешёвых дат с ценами.
- [x] Добавить cross-check подсказку через `flights kb-search --only-carrier U6` / Aviasales, если Kupibilet доступен.
- [x] Добавить в JSON поле `cross_check_commands`.
- [x] Обновить U6-секцию в `flight-search-routing` skill/reference: «price discovery через официальный календарь», workflow `u6-prices` → выбор дат → `kb-search --only-carrier U6` / Aviasales.

## Verification
- [x] Unit test: пустой ответ парсится без exception и не утверждает отсутствие рейсов.
- [x] Unit test: `--date` фильтр работает.
- [x] Unit test: `--limit` / `--sort` работают.
- [x] Unit test: `min_price` / `max_price` и статистика работают.
- [x] Smoke test: human output показывает дешёвые даты и caveat источника.
- [x] JSON output содержит `cross_check_commands`.
- [x] Skill/reference обновлены и не содержат caveat-тяжёлой формулировки, которая обесценивает официальный календарь цен.

## Risks / pitfalls
- U6 calendar endpoint показывает цены по датам, но не доказывает flight availability, номера рейсов или расписание.
- Пустой ответ может означать отсутствие данных у endpoint, ошибку маршрута, временный сбой или limitation источника; нельзя превращать это в уверенный вывод.
- Cross-check через Kupibilet/Aviasales может расходиться с официальным календарём; нужно показывать источник и дату проверки.
- Агрессивное исследование IBE/auth/session API может перейти границы допустимого scope; оно явно исключено из этого плана.

## Status
Current status: done


## Notes
2026-05-05: active-plan audit — verified complete and archived.
Evidence:
- Offline tests: full flights CLI suite passed, including U6 empty response, date filter, price filters, parser args, limit/sort coverage.
- Syntax: `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py` → passed.
- Live JSON smoke: `flights --json u6-prices SVX IST --from-date 2026-07-01 --date 2026-07-19 --sort price --limit 5 --max-price 100000` → `ok=true`, `empty=false`, `priced_dates=1`, `stats` present, `cross_check_commands` present.
- Human output shows dated price table, source caveat, and cross-check commands.
- `flight-search-routing` documents U6 price discovery via `flights u6-prices` and the hierarchy `u6-prices → official IBE API → headless site → aggregator cross-check`.

- 2026-05-05: normalized to `/home/konstantin/docs/plans/README.md` canonical shape; original task scope preserved as checkboxes.
