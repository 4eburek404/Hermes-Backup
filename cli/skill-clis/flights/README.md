# flights CLI

Offline-first flight routing helper for Hermes/Travelpayouts workflows.

The CLI reads local Hermes Travelpayouts cache files, prepares segment-level
search plans, validates airport compatibility, and builds sanitized
Travelpayouts requests. It does not book, buy, or write to Hermes.
Travelpayouts cached API fetches require explicit `request ... --fetch`
commands; provider-specific commands such as `kb-search`, `u6-prices`, and
`route kb-assemble` are live by command name.

## Install

```bash
make install-local
command -v flights
flights --help
flights --json doctor
```

This project uses only the Python standard library.

## JSON Policy

With `--json`, stdout is always an envelope:

```json
{
  "ok": true,
  "command": "route plan",
  "data": {}
}
```

Errors are emitted to stderr:

```json
{
  "ok": false,
  "error": {
    "type": "validation_error",
    "message": "..."
  }
}
```

Tokens are never printed. `doctor` reports only whether
`TRAVELPAYOUTS_TOKEN` and `TRAVELPAYOUTS_MARKER` are present. The CLI reads
process environment first and then auto-loads Travelpayouts keys from
`~/.hermes/.env` without overriding existing environment variables.

## Commands

Runtime check:

```bash
flights --json doctor
```

Static catalog refresh is automatic. Commands that depend on the local
catalog (`cities search`, `airports explain`, `route plan`, `route
kb-assemble`, and `metrics workflow`) refresh missing or stale static files
before running. The default TTL is 7 days.

Useful controls:

```bash
flights --catalog-refresh always --json route plan SVX LHR --depart-date 2026-07-19
flights --catalog-refresh never --json route plan SVX LHR --depart-date 2026-07-19
flights --catalog-max-age 12h --json cities search London
```

Manual no-token Travelpayouts static catalog commands are still available:

```bash
flights --json catalog update
flights --json catalog manifest
```

The static updater writes only canonical files:

```text
countries.json
cities_en.json
cities_ru.json
airports_en.json
airports_ru.json
airlines_en.json
airlines_ru.json
alliances.json
planes.json
routes.json
catalog_manifest.json
```

Resolve city and airport context from local cache:

```bash
flights --json cities search London --limit 5
flights --json airports explain IST SAW SVO DME VKO
```

Build a multi-segment plan without API calls:

```bash
flights --json route plan SVX LON \
  --depart-date 2026-07-19 \
  --return-date 2026-07-23 \
  --hub IST --hub SAW --hub AYT
```

Use local `routes.json` as a broad topology prior to derive one-stop hubs:

```bash
flights --json route plan SVX LHR \
  --depart-date 2026-07-19 \
  --auto-hubs \
  --profile business
```

Validate an assembled itinerary:

```bash
flights --json route validate --profile safe --input itinerary.json
```

Rank multiple itinerary candidates:

```bash
flights --json route rank --profile safe --input candidates.json
flights --json route rank --profile cheap --input candidates.json
```

Parse Travelpayouts results into segment offers:

```bash
flights --json results parse --input svx-ist.raw.json \
  --direction outbound \
  --leg origin_to_hub \
  --origin SVX --destination IST --date 2026-07-19 --currency RUB
```

Assemble parsed segment offers into ranked itinerary candidates:

```bash
flights --json route assemble --profile safe \
  --input svx-ist.parsed.json \
  --input ist-lhr.parsed.json \
  --input lhr-ist.parsed.json \
  --input ist-svx.parsed.json
```

`route assemble` also reports `rejected_pairs` for skipped airport combinations
such as IST/SAW airport changes. Same-airport timing problems, including
negative time order or too-short self-transfers, remain assembled candidates and
are marked `ok=false` by the ranker. Use `--include-rejected-pairs N` to control
how many diagnostics are returned.

Run live Kupibilet direct-only segment searches through hubs, then assemble the
same normalized candidates in one command:

```bash
flights --json route kb-assemble SVX CDG \
  --depart-date 2026-08-15 \
  --return-date 2026-08-19 \
  --hub AYT --hub IST \
  --segment-limit 30 \
  --include-candidates 10
```

`route kb-assemble` is intentionally live: it calls Kupibilet `frontend_search`
for `origin→hub`, `hub→destination`, `destination→hub`, and `hub→origin` direct
segments, including default second-leg day offsets (`outbound: 0,1`; `return:
0,1,2`) so overnight hub departures are not missed. It still returns advisory
aggregator data; final fare, seat availability, baggage, and protected-ticketing
status must be rechecked on the booking screen.

Select carriers explicitly while ranking or assembling:

```bash
flights --json route assemble --profile safe \
  --input svx-ist.parsed.json \
  --input ist-lhr.parsed.json \
  --only-carrier SU --only-carrier TK

flights --json route rank --profile balanced --input candidates.json \
  --prefer-carrier TK --avoid-carrier DP
```

Carrier selection flags:

- `--only-carrier CODE`: hard filter; every segment must use one of the selected carriers.
- `--exclude-carrier CODE`: hard filter; remove candidates using that carrier.
- `--prefer-carrier CODE`: soft preference; demote candidates that do not use a selected carrier.
- `--avoid-carrier CODE`: soft preference; penalize candidates using that carrier.
- `--include-filtered N`: include carrier-filtered diagnostics in JSON.

Build a sanitized Travelpayouts request, still without network:

```bash
flights --json request search SVX IST --depart-date 2026-07-19 --dry-run
```

Read-only cached GraphQL fetch, only when explicitly requested:

```bash
flights --json request search SVX IST --depart-date 2026-07-19 --fetch
```

Probe cached REST Data API prices:

```bash
flights --json request prices-for-dates SVX IST \
  --departure-at 2026-07-19 \
  --direct \
  --fetch

flights --json request grouped-prices SVX IST \
  --departure-at 2026-07 \
  --group-by departure_at \
  --fetch
```

Workflow metrics:

```bash
flights --json metrics workflow SVX LON \
  --depart-date 2026-07-19 \
  --return-date 2026-07-23 \
  --hub IST --hub SAW --hub AYT
```

## What It Automates

- Expands multi-airport cities such as LON into LHR/LGW/STN/LTN.
- Downloads no-token static Travelpayouts catalog files with manifest metadata
  (`downloaded_at`, `url`, `count`, `sha256`, `schema_version`).
- Uses `routes.json` locally for direct route evidence and one-stop hub discovery.
- Keeps IST and SAW separate and flags airport changes.
- Keeps SVO, DME, and VKO separate for Moscow routing.
- Prepares segment-by-segment Travelpayouts cached GraphQL requests instead of using broad
  city codes that often return empty cache data.
- Builds cached REST Data API probes for `prices_for_dates` and `grouped_prices`.
- Parses Travelpayouts `prices_one_way` / `prices_round_trip` responses into
  normalized segment offers, preserving provider `transfers` metadata such as
  `duration_seconds`, `night_transfer`, and `visa_required`.
- Assembles compatible segment offers into outbound/return journeys.
- Can run Kupibilet direct-only segment searches through hubs and assemble those
  live normalized offers via `route kb-assemble`.
- Scores connection risk, internal transfer metadata, and airport changes, then
  ranks candidates by profile.
- Supports explicit carrier selection and carrier preferences for ranked
  candidates.
- Computes deterministic workflow metrics so the manual work can be compared
  with the CLI-assisted path.

## Risk Profiles

Profiles change ranking, not the underlying safety checks.

| Profile | Rank order | Use when |
|---|---|---|
| `safe` | reject → risk → elapsed → price | best connection quality matters most |
| `balanced` | reject → risk → price → elapsed | default tradeoff |
| `cheap` | reject → price → risk → elapsed | price matters, but unsafe transfers still sink |
| `business` | reject → risk → elapsed → price | predictable same-airport travel matters |

Risk grades:

- `excellent`: 0-20
- `good`: 21-40
- `risky`: 41-70
- `reject`: 71-100

`route validate` accepts one itinerary:

```json
{
  "price": 92817,
  "segments": [
    {
      "origin": "SVX",
      "destination": "IST",
      "departure_at": "2026-07-19T10:30:00",
      "arrival_at": "2026-07-19T13:55:00",
      "carrier": "SU"
    },
    {
      "origin": "IST",
      "destination": "LHR",
      "departure_at": "2026-07-19T20:25:00",
      "arrival_at": "2026-07-19T22:25:00",
      "carrier": "TK"
    }
  ]
}
```

`route rank` accepts either a JSON list or an object with `itineraries` or
`candidates`. Each candidate may include `id`, `price`, `currency`, `ticketing`,
and `segments`.

Both `route rank` and `route assemble` return `carrier_policy`. Hard carrier
filters remove candidates from `ranked` and report examples under
`carrier_policy.filtered`; soft preferences add carrier risk components and
adjust `rank_key`.

`route assemble` accepts parsed result JSON from `results parse`. Each parsed
result has:

```json
{
  "segment_result": {
    "direction": "outbound",
    "leg": "origin_to_hub",
    "query": {"origin": "SVX", "destination": "IST", "date": "2026-07-19"},
    "offers": []
  }
}
```

Assembly pairs:

- outbound: `origin_to_hub` + `hub_to_destination`
- return: `destination_to_hub` + `hub_to_origin`

Pairs only assemble when the first offer arrival airport equals the second offer
departure airport. Skipped airport-mismatch and cross-airport pairs are returned
as `rejected_pairs` with `reason`, `airport_pair_status`, `arrival_airport`,
`departure_airport`, `actual_min`, `required_min`, `risk`, and source offer
summaries. Same-airport timing violations are assembled and then scored by the
ranker as invalid candidates.

For `prices_round_trip`, `results parse --direction outbound` selects the first
trip segment and `--direction return` selects the second trip segment. If the
provider returns no round-trip items, the parser returns zero offers without
inventing candidates.

## Non-goals

- No booking or purchase.
- No hidden writes outside the static catalog cache. Catalog-dependent commands
  can automatically update `~/.hermes/plugins/travelpayouts-flights/cache`.
- No Docker Hermes access.
- No Travelpayouts cached price/Data API network fetch unless `--fetch` is
  passed on a `request` command. Static catalog refresh is separate and
  requires no token.
- `kb-search`, `u6-prices`, and `route kb-assemble` are explicit live provider commands.
