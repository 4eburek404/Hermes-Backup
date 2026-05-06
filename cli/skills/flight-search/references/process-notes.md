# Flight Search Process Notes

Use these notes when analyzing a flight-search run or improving the Hermes flights CLI.

## Lessons From The SVX-LHR Run

Request: `SVX-LHR` on `2026-07-19`, return `LHR-SVX` on `2026-07-24`. The user typed `sxv`; context implied `SVX`, so the agent stated the assumption.

Observed flow:

1. `doctor` showed an empty static catalog cache and no Travelpayouts token.
2. `route plan` refreshed the no-token catalog and used a broad pre-strategy hub list.
3. Several broad-list hubs were not live-viable for the dates.
4. A broad Kupibilet live assembly with `IST,SAW,AYT,GYD,DXB,DOH` ran 42 segment searches.
5. Segment matrix showed:
   - `IST` and `DXB` had enough matching legs to build full options.
   - `DOH` had London legs but no SVX legs.
   - `AYT` and `GYD` had SVX legs but no LHR legs.
   - `SAW` was effectively empty for this route/date.
6. The first assembly returned 50 candidates, all rejected. The cap selected cheap invalid combinations before enough valid ones were retained.
7. A narrowed rerun with `IST,DXB`, `--max-candidates 1000`, and `--include-candidates 1000` exposed 503 valid candidates.
8. Direct one-way Kupibilet searches found cheaper provider-assembled options, but with 2-4 transfers, airport changes, long waits, and low-cost carriers. They were not better business-travel choices.

Best business-safe result found:

- `117620 RUB`
- Outbound: `SVX-IST SU630`, `4h55` layover, `IST-LHR BA719`
- Return: `LHR-IST TK1980`, `2h30` layover, `IST-SVX U6774`
- Risk: `excellent`, but still advisory until booking screen recheck

## Bottlenecks

- Segment searches are sequential and slow on broad hub sets.
- No short-lived cache for repeated Kupibilet segment probes; narrowing reruns re-fetch the same segments.
- Without `TRAVELPAYOUTS_TOKEN`, cached REST/GraphQL probes are unavailable, so pruning relies on live provider calls.
- A pre-ranking candidate cap can hide valid options behind cheap rejected combinations.
- `ranked` IDs and included raw candidate bodies can diverge if the contract does not include full top-ranked candidates.

## CLI Improvement Ideas

High priority:

- Use default `ru-priority` first for Russia-origin routes: IST direct, SVO/SU fallback only if IST direct is empty, then DXB direct only if IST has no usable assembled pair.
- Use the broad built-in hub list only through `--routing-strategy hub-list`, then narrow live searches with explicit `--hub` values after reading viability.
- Use `live_search.hub_viability` to report offer counts for every required leg before trusting assembly.
- Rank/filter valid pairs before applying `--max-candidates`; maintain a separate raw `--candidate-pool-limit`.
- Use `--include-ranked-candidates N` so full details for the top ranked candidates are always included.
- Add a short-lived segment response cache keyed by provider, route, date, direct-only, currency, carrier filters, and limit.

Medium priority:

- Add profile-aware hub pruning: business profile should prefer same-airport hubs, fewer carriers, and reasonable layovers.
- Use REST `prices_for_dates direct=true` as a cheap cached leg probe when `TRAVELPAYOUTS_TOKEN` exists.
- Use `grouped_prices` for date-window work before live providers.
- Emit a concise human-readable "boevoi" report directly from `route kb-assemble`.
- Include one-way provider-assembled controls in the report, but label them separately from self-transfer hub assembly.

Known traps:

- Do not call Travelpayouts cached APIs "live"; only Kupibilet live aggregate should be called live.
- Do not report candidates with `ok=false` as recommendations.
- Do not assume the cheapest provider result is business-viable.
