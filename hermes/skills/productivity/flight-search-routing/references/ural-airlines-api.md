# Ural Airlines (U6) — API & Search Hierarchy

## CLI Access

```bash
flights u6-prices SVX IST --from-date 2026-07-01     # Daily min prices (~92 days)
flights u6-prices SVX IST --from-date 2026-07-01 --date 2026-07-19  # Specific date
flights u6-prices SVX IST --from-date 2026-07-01 --min-price 20000 --max-price 30000
```

For full CLI options, call `flights u6-prices --help`.

## API Endpoint (for reference/troubleshooting)

```
GET https://www.uralairlines.ru/ajax.php?component=schedule&action=mobile_calendar
  &departureCityIata={ORIG}&arrivalCityIata={DEST}&fromDate={YYYY-MM-DD}&lang=ru&updated=true
Headers: X-Requested-With: XMLHttpRequest, Referer: https://www.uralairlines.ru/
```

Returns: `{dates: [{date, price: {code, price}}]}` for ~92 days. One-way minimum prices only (no flight numbers, times, or availability).

**⚠️ `price: null` ≠ no flight exists.** It may mean no U6 sale on that date, seasonal gap, or calendar incompleteness. Cross-check with aggregators before concluding a route doesn't exist.

## Active Search Hierarchy

When U6 search looks incomplete, **do not stop at caveats**. Investigate and improve:

1. **Fast signal:** `flights u6-prices` — daily minimum prices
2. **Stronger path:** Official IBE API (`u6ibe.book.uralairlines.ru/api/v2.3/`) — `Session`, `flights/search`, `Calendar/ScheduleByDay`. Provides flight numbers, times, fares. Prefer this over repeating "calendar lacks flight numbers."
3. **Fallback:** Headless official site (see `browser-headless-workflows.md`)
4. **Cross-check:** Aggregators / manual Aviasales / airline verification

Output discipline: state what was actively checked (calendar, IBE, headless, aggregate), what each source proves, and what remains unverified. Never present `price:null` or empty results as definitive "U6 has no flight."

## Security Note

The booking SPA exposes `env.json` at `https://book.uralairlines.ru/37546/env/env.json` containing `API_URL`. Do **not** print or store `API_KEY`, `ADMITAD_API_KEY`, `AVIASALES_API_KEY`, or other credential fields.