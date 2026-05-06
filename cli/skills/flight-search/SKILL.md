---
name: flight-search
description: Use when Codex needs to find, plan, compare, or diagnose flight options with the Hermes flights CLI, Aviasales/Travelpayouts cached data, or Kupibilet live aggregate search. Triggers include user requests for airfare, tickets, routes, hub planning, "boevoi" live flight search, SVX/LHR-style IATA searches, date-window flight probes, or improvements to the flight-search workflow.
---

# Flight Search

## Overview

Use the companion CLI in `cli/skill-clis/flights` to plan offline first, then probe cached or live providers explicitly. Treat the result as advisory until the booking screen confirms price, availability, baggage, and ticket protection.

## Locate the CLI

From the Hermes repository root, use:

```bash
cd cli/skill-clis/flights
python3 -m flights_cli --json doctor
```

Prefer `python3 -m flights_cli` from that directory so the checked-out code is used. Use the installed `flights` command only after confirming it points to the same build.

## Search Workflow

1. Normalize the request.
   - Convert dates to exact dates before searching.
   - Normalize IATA codes. If the user types an unlikely code such as `SXV` but the route context strongly implies `SVX`, state the assumption before using it.
   - Prefer airport codes such as `LHR` over broad city codes such as `LON` when the user specifies an airport.

2. Run `doctor`.
   - Note whether static catalog files exist and whether `TRAVELPAYOUTS_TOKEN` is present.
   - Static catalog refresh is allowed and tokenless; Travelpayouts price/Data API fetches require explicit `request ... --fetch`.

3. Build the local plan.

```bash
python3 -m flights_cli --json route plan ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business
```

When no `--hub` is supplied, `--routing-strategy auto` uses `ru-priority`:

1. Check exact-airport direct controls: `origin→destination`, and `destination→origin` for round trips. In live `route kb-assemble`, use the official Koltsovo seasonal route index as a cached negative filter for any direct control that includes SVX. Do not add a static "known no direct" skip table.
2. Check `origin→IST` direct first, then `IST→destination`.
3. If `origin→IST` has no viable direct offer, check `origin→SVO→IST` with Aeroflot/SU and reuse `IST→destination`.
4. Check `origin→DXB→destination` only when direct/SVO/IST priority routes do not produce a usable assembled pair. Do not expand DXB through Moscow.

Carrier priority is `U6`, `SU`, `TK`; SVO fallback legs are constrained to `SU`.

For Asia, China, and Oceania destinations, `ru-priority` becomes geo-aware:
check SVO as an independent hub before IST/DXB. Beijing `BJS` expands to
`PEK`/`PKX`; Paris `PAR` expands to `CDG`/`ORY`.

Use `--routing-strategy hub-list` or pass explicit `--hub` values only when you intentionally need a broader hub matrix.

Built-in hubs:

- `IST`: broadest option from Russia.
- `DXB`: main competitor, especially for Asia, Africa, and Australia.
- `DOH`: strong long-haul hub via Qatar.
- `AUH`: useful backup for DXB and DOH.
- `BEG`: Europe plus some North America, but not worldwide.
- `TAS`, `GYD`: regional and partial long-haul routes.
- `PEK`, `PVG`, `CAN`: use when the destination geography is Asia, China, or Oceania.
- `ADD`, `CAI`, `MCT`, `SHJ`: niche hubs for Africa, Middle East, India, and price.

4. Use cached Travelpayouts only when credentials exist.

```bash
python3 -m flights_cli --json request prices-for-dates ORIGIN DEST \
  --departure-at YYYY-MM-DD --direct --fetch

python3 -m flights_cli --json request grouped-prices ORIGIN DEST \
  --departure-at YYYY-MM --group-by departure_at --fetch
```

Call these cached probes, not live search.

5. Probe live segments with Kupibilet.

For live `route kb-assemble`, the default `ru-priority` strategy runs exact direct controls plus direct-only hub probes, skips the SVO fallback when direct IST offers exist, synthesizes `origin→IST` from `origin→SVO + SVO→IST` when direct IST is empty, and skips DXB when direct/SVO/IST already has a non-error assembled journey. Start `hub-list` only when you intentionally want a broad matrix.

```bash
python3 -m flights_cli --json route kb-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business \
  --segment-limit 30 \
  --candidate-pool-limit 5000 \
  --max-candidates 50 \
  --limit-per-pair 30 \
  --include-ranked-candidates 10 \
  --include-segment-results 0
```

Kupibilet segment probes use a short-lived cache by default (`--live-cache-ttl-seconds`, 6 hours). `route kb-assemble` also uses a separate official SVX direct-route index cache (`--direct-route-index-ttl-seconds`, 7 days) to skip absent exact direct controls such as SVX→MUC before calling Kupibilet. Use `--no-direct-route-intel` only when the user wants to ignore the official schedule index. `kb-search` has matching live-result `--cache-ttl-seconds` and `--no-cache` controls.

Start broad only to learn the segment matrix. Then read `live_search.hub_viability`, narrow to hubs that have offers for all needed legs, and rerun with a sufficient candidate pool.

6. Use direct one-way live search as a control.

```bash
python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --currency RUB \
  --limit 20
```

This shows provider-assembled one-way options, often with low-cost carriers, long waits, airport changes, or multiple transfers. Do not mix these into a business-safe self-transfer result without validating every connection.

## Analysis Rules

- Read `live_search.hub_viability` and `live_search.segment_searches` before trusting candidates. A hub is viable only if all required legs have nonzero offers for the chosen dates and offsets.
- Read `live_search.direct_route_intelligence` when direct controls were skipped. A `direct_route_schedule_negative` skip means the exact SVX airport pair was absent from the official seasonal route index; hub routing still ran.
- If all ranked candidates are rejected, inspect `assembly.candidate_pool_truncated`, hub viability, and pair rejections. Rerun with narrower hubs or a higher `--candidate-pool-limit`.
- Use `ranked_candidates` for exact top-ranked flight details. `candidates` is only a raw candidate sample.
- `route assemble` can mix direct and hub journeys. It may return a hub outbound with a direct return, or the reverse.
- Filter to `ok=true` before reporting recommendations. Summarize rejected options only as warnings or "do not take" notes.
- For business travel, prefer same-airport hubs, 2-6 hour connections, fewer carriers, and no airport changes. Penalize long overnight waits even when the price is lower.
- Always distinguish source type: static catalog, Travelpayouts cached Data API, Travelpayouts GraphQL cached API, or Kupibilet live aggregate.

## Report Shape

Lead with the best viable option and explain why. Include:

- route, dates, price, source, and whether the itinerary is validated by the CLI
- each flight number, departure/arrival time with timezone offset, and layover duration
- risk grade and concrete caveats
- a cheaper-but-worse comparison when useful
- a final note that live aggregate data must be rechecked on the booking screen

## References

Read [process-notes.md](references/process-notes.md) when diagnosing search quality, improving the CLI workflow, or explaining bottlenecks from a live search run.
