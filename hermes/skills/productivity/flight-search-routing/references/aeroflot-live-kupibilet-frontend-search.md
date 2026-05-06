# Aeroflot Live Search via Kupibilet

## Rule

For Aeroflot questions, use **one CLI workflow**:

```bash
flights --json kb-search SVX MOW --depart-date 2026-07-19 --only-carrier SU --direct-only --limit 20
```

For full options, call `flights kb-search --help`.

## Key Insights

- Filter "Аэрофлот" by **marketing or operating carrier `SU`**, not operating-only — Rossiya-operated `FV` flights sold as SU are valid Aeroflot options.
- **Deduplicate Kupibilet variants** by `flight_number + departure_time + arrival_time`. Raw variants are fare/sale variants, not distinct flights. SVX→MOW may show many SU "variants" that are 11 unique direct flights.
- Final ticketing truth requires checking the seller/airline before purchase — Kupibilet is a live aggregate, not official `aeroflot.ru` inventory.
- **Do NOT use or reintroduce the removed `su-flights` legacy command** — it was cached, operating-carrier-only, and missed MOW city-code results and SU-marketed Rossiya (FV) flights.

## Kupibilet `frontend_search` Details

CLI `flights kb-search` abstracts the Kupibilet `frontend_search` API. You should not need to call this API directly. If `kb-search` doesn't cover a use case, check `flights kb-search --help` first, then consider a headless browser search (see `browser-headless-workflows.md`).