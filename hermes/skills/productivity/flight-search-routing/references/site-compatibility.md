# Site Compatibility Details

Per-site notes, sanctions rules, and decision tree. Compact version of the matrix is in SKILL.md.

## Google Flights / `fli` — Sanctions Rules

- **Sanctions are departure-based, not IP/locale-based.** Routes originating in Russia → only Flydubai/Emirates via Dubai at 3-4× overprice. SVX→IST TK filter returns 0 results.
- **`gl=GB&hl=en` locale bypass does NOT help** — same sanctions regardless.
- **Segment search bypasses sanctions** for non-Russian-origin legs: IST→LON, LON→IST, even IST→SVX (shows Azerbaijan Airlines via GYD). Search each non-Russian segment separately.
- **For SVX→anything:** use Travelpayouts / Kupibilet / U6 CLI. Never `fli`.

### Segment Search Workflow (non-Russian legs only)

1. One-way mode: `fli flights IST LHR 2026-07-19 --airlines TK --currency RUB`
2. Airline filter works normally for non-Russian routes
3. Extract via `--format json` or text
4. Combine segment prices for cost estimate; warn about separate-ticket risk
5. For Russian-origin segment: use Travelpayouts/Kupibilet/U6

## Kupibilet — Key Notes

- **URL navigation is a dead end** — always homepage + form fill (see `browser-headless-workflows.md`)
- **"Откуда" field concatenates** — must clear via JS before typing
- Results heavily favor **AYT (Antalya) routing** — IST→LHR doesn't always appear
- **Price calendar is asymmetric** — ±1 day can save 8-10k₽; always show week view
- London airport change across stay = acceptable open-jaw, NOT same-day transfer
- Kupibilet `LON` city-code works for live search (unlike Travelpayouts)

## Aviasales (Manual Only)

Best aggregator for Russian-origin flights but **blocks headless** (reCAPTCHA v2).

Direct link format: `https://www.aviasales.ru/search/SVX1907LON2307` → `[ORIGIN][DD][MM][DEST][DD][MM]`

UI: SPA loads after transition; calendar overlay → press Escape to dismiss.

## Blocked Sites (No Workaround)

| Site | Block Type | Note |
|---|---|---|
| Skyscanner | Captcha | Headless blocked |
| Kayak/Momondo | Redirect | Drops search params |
| Trip.com | Empty results | GDS gap for SVX→LON |
| Yandex.Travel | 404 | Avia search discontinued |
| OneTwoTrip | URL 404 | Old URL patterns broken |
| Aeroflot | IP block | NGenix bot-challenge on cloud IPs |
| Turkish Airlines | HTTP2 error | `net::ERR_HTTP2_PROTOCOL_ERROR` in headless |