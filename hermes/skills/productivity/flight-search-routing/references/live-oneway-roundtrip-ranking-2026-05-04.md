# Live one-way assembly when round-trip search is empty (2026-05-04)

Session-derived pattern from SVX↔LON, dates 2026-07-19 / 2026-07-24.

## Trigger

Use this when a user asks for round-trip availability/prices and the direct round-trip source returns empty or sparse results, especially for Russian-origin routes and city codes like `LON`.

## What worked

1. Build an offline plan first to identify city airports/hubs and current layover defaults:

```bash
flights --json route plan SVX LON \
  --depart-date 2026-07-19 \
  --return-date 2026-07-24 \
  --hub IST --hub SAW --hub AYT --hub DXB --hub GYD
```

2. Try direct round-trip Travelpayouts/Aviasales, but treat empty results as a source limitation, not proof of no route.

3. Query one-way city-pairs separately:

```bash
flights --json kb-search SVX LON --depart-date 2026-07-19 --limit 20 > /tmp/kb_out.json
flights --json kb-search LON SVX --depart-date 2026-07-24 --limit 20 > /tmp/kb_ret.json
```

4. Query useful segment pairs for cross-checks and hidden alternatives, e.g.:

```bash
flights --json kb-search SVX EVN --depart-date 2026-07-19 --limit 5
flights --json kb-search EVN LON --depart-date 2026-07-20 --limit 5
flights --json kb-search SVX AYT --depart-date 2026-07-19 --limit 5
flights --json kb-search AYT LON --depart-date 2026-07-19 --limit 5
flights --json kb-search LON IST --depart-date 2026-07-24 --limit 5
flights --json kb-search IST SVX --depart-date 2026-07-24 --limit 5
```

5. Assemble candidate JSON from outbound × return one-way offers, preserving each direction as a separate `journey`, then rank:

```bash
flights --json route rank \
  --input /tmp/kb_roundtrip_candidates.json \
  --profile balanced \
  --ticketing separate \
  --min-same-airport-min 90 \
  --min-cross-airport-min 300
```

Candidate shape accepted by `route rank`:

```json
{
  "candidates": [
    {
      "id": "kb-combo-1",
      "price": 68261,
      "currency": "RUB",
      "ticketing": "separate",
      "journeys": [
        {"direction": "outbound", "segments": [{"origin":"SVX", "destination":"EVN", "departure_at":"...", "arrival_at":"...", "flight_number":"3F478", "carrier":"3F"}]},
        {"direction": "return", "segments": [{"origin":"LGW", "destination":"AYT", "departure_at":"...", "arrival_at":"...", "flight_number":"W95707", "carrier":"W9"}]}
      ]
    }
  ]
}
```

## Ranking notes

- Do not rank by price alone. In this session, the cheapest valid no-Schengen option was much less practical because it arrived in London on 21.07 after a long EVN layover.
- Add an explicit Schengen flag for `FCO`, `OTP`, `CDG`, `BVA`, `WAW`, etc. `route rank` validates connection timing/airports but does not decide visa suitability.
- Treat same-airport separate-ticket minimum as 90 min, same-airport business-preferred as 120 min, and cross-airport as 300 min unless the user overrides. Label 90–119 min as tight.
- If a source reports a round-trip count of zero but one-way searches find options, explain this as a source/query limitation.

## Source caveats

- Kupibilet frontend search is a live aggregate, not the airline source of truth.
- Travelpayouts/Aviasales prices can be cached and must be rechecked before purchase.
- U6 official calendar is useful for U6 segment price floors, not full itinerary validation.
