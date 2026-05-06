# SVX ↔ London 2026-07-19/23 — live Kupibilet round-trip workflow

Session-specific detail from a live search for:
- outbound: `SVX → LON`, `2026-07-19`
- return: `LON → SVX`, `2026-07-23`
- currency: RUB

## Why this reference matters

For Russia→London routes, `LON` is useful in Kupibilet live aggregate even though older Travelpayouts cache often required specific London airports. The best practical results may be multi-airport London open-jaw combinations (`LGW` in, `LTN`/`LHR` out), and the cheapest raw results are often poor because they arrive too late or include risky Schengen/short connections.

## Live aggregate commands used

```bash
flights --json kb-search SVX LON --depart-date 2026-07-19 --limit 5
flights --json kb-search LON SVX --depart-date 2026-07-23 --limit 5
```

Observed one-way summaries:
- `SVX → LON 2026-07-19`: source `Kupibilet frontend_search (live aggregate)`, raw variants `536`, unique itineraries `282`.
- `LON → SVX 2026-07-23`: source `Kupibilet frontend_search (live aggregate)`, raw variants `508`, unique itineraries `289`.

For round-trip combinations, use Kupibilet `frontend_search` with two trips in one payload:

```json
{
  "trips": [
    {"departure": "SVX", "arrival": "LON", "date": "2026-07-19"},
    {"departure": "LON", "arrival": "SVX", "date": "2026-07-23"}
  ],
  "travelers": {"adult": 1, "child": 0, "infant": 0},
  "cabin": "economy",
  "agent": "kupibilet",
  "lang": "ru",
  "currency": "RUB",
  "client_platform": "web",
  "filters": {},
  "sort_by": "price",
  "short_response": false
}
```

Observed round-trip summary:
- HTTP `200`
- raw variants `3476`
- deduped unique itinerary keys `2000`
- same-airport intra-connection candidates `949`
- same-airport + every connection ≥3h candidates `328`

## Ranking / filtering lessons

Do not present the absolute cheapest result as the recommendation without time/risk filtering.

Useful filters for SVX↔LON:
1. Remove intra-connection airport mismatches (`arrival airport != next departure airport`) unless explicitly presenting a self-transfer warning.
2. Prefer same-airport connection time ≥3h for international separate tickets.
3. Separate “arrives in London on 19 Jul” from “arrives 20/21 Jul”; cheap EVN/Wizz routes may waste most of the trip.
4. Flag Schengen transit risk (e.g., ZRH/HAM/MXP/WAW/BCN) if tickets may be separate or bags not checked through.
5. For London, open-jaw airport changes across the stay are acceptable (`LGW` in, `LTN`/`LHR` out), but same-day connections between London airports are not.

## Representative live results

### Practical first pick: about 81,443 RUB

Outbound, arrives London on 19 Jul:
- `2S126` SVX 2026-07-19 03:20 +05 → AYT 06:20 +03
- layover AYT: 3h40
- `XC4108` AYT 10:00 +03 → LGW 13:30 +01

Return:
- `W95331` LTN 2026-07-23 15:00 +01 → AYT 21:35 +03
- layover/overnight AYT: 22h20
- `2S125` AYT 2026-07-24 19:55 +03 → SVX 2026-07-25 02:25 +05

Why: only 2 total stops, no obvious Schengen self-transfer, London arrival on 19 Jul. Downsides: overnight/day in Antalya and return arrival after midnight on 25 Jul.

### Cheaper but worse timing: about 78,102 RUB

Outbound arrives 20 Jul:
- `2S126` SVX 2026-07-19 03:20 +05 → AYT 06:20 +03
- long layover AYT: 26h40
- `XQ590` AYT 2026-07-20 09:00 +03 → LGW 11:40 +01

Return:
- `LX339` LHR 2026-07-23 20:05 +01 → ZRH 22:45 +02
- `LX8186`/WK ZRH 2026-07-24 06:40 +02 → AYT 10:55 +03
- `2S125` AYT 19:55 +03 → SVX 2026-07-25 02:25 +05

Downsides: loses a day in London and includes Schengen transit risk.

### Cheapest observed but poor recommendation: about 72,469 RUB

Outbound:
- `3F478` SVX 2026-07-19 11:20 +05 → EVN 14:00 +04
- layover EVN: 33h10
- `W95312` EVN 2026-07-20 23:10 +04 → LTN 2026-07-21 01:35 +01

Return:
- `LGW → MXP → WAW → EVN → SVX`, including `WAW` layover around 1h.

Why poor: arrival in London only on 21 Jul, 3-stop return, short Schengen connection.

### If return by 24 Jul matters: about 82,015 RUB

Outbound:
- `2S126` SVX → AYT
- `XC4108` AYT → LGW, arrives 19 Jul 13:30

Return:
- `EW7461` LHR 2026-07-23 08:45 +01 → HAM 11:20 +02
- long HAM layover 22h40
- `W67806` HAM 2026-07-24 10:00 +02 → EVN 16:10 +04
- `U62950` EVN 19:15 +04 → SVX 23:30 +05

Upside: back on 24 Jul. Downside: Germany/Schengen transit risk.

## Segment cross-checks

Use `fli` only for non-Russian/open segments as a sanity check:

```bash
fli flights AYT LGW 2026-07-20 --format json --currency RUB --all --sort CHEAPEST
fli flights LTN AYT 2026-07-23 --format json --currency RUB --all --sort CHEAPEST
fli flights IST LHR 2026-07-19 --format json --currency RUB --all --sort CHEAPEST
```

Observed confirmations:
- `AYT → LGW 2026-07-20`: Google/fli found `XQ590` around 3,166 RUB and `XC4108` around 3,491 RUB.
- `LTN → AYT 2026-07-23`: found `XQ531`, `U22565`; Wizz may show zero/missing price in `fli`, so do not rely on Google price alone for Wizz.
- `IST → LHR 2026-07-19`: found many direct BA/TK options.
- `LGW → IST 2026-07-23`: Google/fli may underprice/zero Wizz; use as schedule sanity, not final seller price.

Use `flights u6-prices` for U6-only calendars:
- `SVX↔IST` has priced U6 calendar data.
- `SVX↔AYT` returned no priced U6 dates in this session, so Antalya routing came from Kupibilet live aggregate, not U6 calendar.

## Presentation guidance

When reporting to Konstantin:
- lead with the best practical itinerary, not the cheapest raw hit;
- explicitly say the year assumed and source type;
- separate “checked facts” from caveats;
- explain how the search was done after the options if the user asks “потом расскажешь, как искал”.
