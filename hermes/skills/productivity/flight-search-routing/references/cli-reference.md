# CLI Insights

Unique insights that CLI `--help` won't tell you. For command syntax and options, call `flights <cmd> --help` or `fli --help`.

## Key Insights

- **One-way queries return more results than round-trip** in Travelpayouts API. Direct round-trip cache can return `0` even when both one-way direct legs exist (seen on `SVX→PKX 2026-08-05` + `PKX→SVX 2026-08-10` U6). For round-trip/direct checks, search each direction as one-way and then combine/filter; treat cached round-trip absence as a source limitation, not evidence of no flights.
- **Filter by `operating_carrier` per leg in JSON, not `main_airline`** — SU-marketed ticket may have FV (Rossiya) or XQ (SunExpress) operating second leg. `main_airline` alone is insufficient.
- **For business LHR searches, stitch U6 Russia-origin segments separately** — `kb-search SVX LON/LHR --only-carrier U6` can return 0 because it filters out mixed-carrier U6+BA/TK itineraries. Search `SVX→IST` with `u6-prices` / `kb-search --only-carrier U6`, then combine with direct `IST→LHR` BA/TK options and validate transfer buffers.
- **Do not let `route assemble` truncate frontier-relevant options before ranking** — its default segment depth is now `--limit-per-pair 10` because single-axis sorted segment lists (price, duration, departure time, source relevance) can hide options that are materially better on another axis below the first five. Use 10+ for business/complex assembly and explicitly keep schedule, duration, connection-safety, airport/carrier, and price representatives before final ranking.
- **For business routing, surface tight frontier candidates with `--min-same-airport-min 90` but rank 90–119 min as tight and ≥120 min as business-preferred** — this prevents the CLI's 120-min default from hiding minimum-acceptable options while preserving the answer distinction between tight and preferred buffers.
- **For `route kb-assemble` JSON, recommend from `data.ranked`, not raw `data.candidates`** — `data.candidates` is an included sample/raw candidate block and can contain combinations that later fail time-order or airport-compatibility checks. Final shortlist must use `data.ranked` entries with `ok=true`, `validation_summary.violation_count=0`, and their `connections`; use `data.rejected_pairs` to explain rejected cheap/bad options.
- **`route kb-assemble --hub IST` can still receive `SAW` offers in the `IST→...` segment result** — provider city/airport relaxation can let cheap secondary-airport offers consume `--limit-per-pair` slots. If exact/preferred-airport or carrier quality matters, inspect `data.segment_results`, raise `--limit-per-pair`/`--segment-limit`, and manually preserve same-day actual-`IST` carrier representatives from `fli`/segment results before final ranking (e.g. TK flights that appear after cheaper SAW/LH rows).
- **`fli` does NOT accept city code LON** — only specific airports (LHR, LGW, STN, LTN). Passing LON → `validation_error`.
- **`fli` / Google Flights sanctions are route-based (departure in Russia)** — SVX→IST TK returns 0 results; IST→LHR TK works fine. Use `fli` only for non-Russian-origin segments.
- **Do NOT use or reintroduce the removed `su-flights` legacy command** — it was cached, operating-carrier-only, and missed MOW city-code results and SU-marketed Rossiya (FV) flights. Use `flights kb-search ... --only-carrier SU` instead.

## Source Comparison

| Source | RU sanctions? | Cache/Live | Airline filter | Speed | Best for |
|---|---|---|---|---|---|
| `flights kb-search` | ✅ | Live aggregate | ✅ `--only-carrier` | 5-20s | SU/U6/any carrier; live city-pair prices |
| `flights route kb-assemble` | ✅ | Live aggregate direct segments | ✅ carrier filters/preferences | multi-call | Russia↔Europe one-stop/hub questions; searches direct-only legs through hubs and assembles compatible pairs |
| `flights u6-prices` | ✅ | Live | ✅ (U6 only) | 1s | U6 daily min prices |
| `fli` CLI | ❌ hides SU/U6/TK from SVX | Live (Google) | ✅ `--airlines` | 3-5s | Non-RU segments only |
| Travelpayouts API | ✅ shows SU/U6 | Cached (1-3 days) | ⚠️ post-filter | 2-3s | Last sanity/price-link layer only; never negative evidence |
| Kupibilet headless | ✅ shows SU/U6 | Live aggregate | ⚠️ post-filter | 5-30s | Price calendar, live routes |
| Ural Airlines headless | ✅ (U6 only) | Live | ❌ | 15-30s | U6 flights + details |

## Optimal Pipeline (Russia↔Europe)

1. `flights --json route plan ... --hub IST` — offline routing plan; `--hub` is repeatable
2. For Russia↔Europe one-stop/hub-specific questions: `flights --json route kb-assemble ORIGIN DEST --depart-date ... --return-date ... --hub IST --hub AYT ...` — live Kupibilet direct-only segment search + assembly; run before answering from aggregate one-stop results
3. `flights --json u6-prices` — fast U6 price signal for SVX→IST or other U6 segments
4. `flights --json kb-search` / `flights --json request search --live` — live/cached city-pair or single-segment checks
5. `fli flights` — non-Russian segments (IST/SAW↔Europe)
6. Manual Aviasales/airline verification before ticketing