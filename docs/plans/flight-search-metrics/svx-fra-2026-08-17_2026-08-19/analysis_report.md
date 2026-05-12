# SVX–FRA flight search metrics and timing analysis

Created: 2026-05-09T19:09:28.049215+00:00

## Request
- Route: SVX→FRA 2026-08-17; FRA→SVX 2026-08-19
- Profile: business / operational frontier
- Dates interpreted as upcoming 2026 dates.

## Key saved artifacts
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/metrics_summary.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/diagnostics_summary.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/algorithm_diagnostics.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/pool20000_summary.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/live_assemble_business_agent_brief.stdout.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/live_assemble_business_agent_brief_pool20000.stdout.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/live_assemble_business_debug_nocache.stdout.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/kb_search_outbound_aggregate_nocache.stdout.json`
- `/home/konstantin/docs/plans/flight-search-metrics/svx-fra-2026-08-17_2026-08-19/kb_search_return_aggregate_nocache.stdout.json`

## Runtime metrics
- doctor: 0.369s, rc=0, json_ok=True, stdout=7105 bytes
- live_assemble_business_agent_brief: 11.89s, rc=0, json_ok=True, stdout=71812 bytes
- live_assemble_business_debug_nocache: 15.729s, rc=0, json_ok=True, stdout=2143136 bytes
- kb_search_outbound_aggregate_nocache: 1.293s, rc=0, json_ok=True, stdout=21681 bytes
- kb_search_return_aggregate_nocache: 1.402s, rc=0, json_ok=True, stdout=21197 bytes
- kb_search_outbound_direct_nocache: 1.274s, rc=0, json_ok=True, stdout=1626 bytes
- kb_search_return_direct_nocache: 1.436s, rc=0, json_ok=True, stdout=1626 bytes
- live_assemble_business_agent_brief_pool20000: 5.748s, rc=0, json_ok=True, stdout=46235 bytes

## Current best operational result after diagnostics
- Best expanded-pool CLI result: 93 751 RUB, elapsed 23h40, risk=excellent/0, stop tier=T1_ONE_STOP
  - U6773 SVX 2026-08-17T07:20:00+05:00 → IST 2026-08-17T10:50:00+03:00 (U6)
  - LH1299 IST 2026-08-17T13:55:00 → FRA 2026-08-17T16:05:00 (LH)
  - TK1588 FRA 2026-08-19T11:30:00 → IST 2026-08-19T15:40:00 (TK)
  - U6774 IST 2026-08-19T19:45:00+03:00 → SVX 2026-08-20T02:25:00+05:00 (U6)
  - connection outbound at IST: 3h05 (required 2h)
  - connection return at IST: 4h05 (required 2h)
- Ticketing boundary: Assume separate/self-transfer until the booking screen confirms protected through-ticketing and baggage.
- Alternative all-preferred-ish: 91 917 RUB, elapsed 24h10: SU630 SVX→IST | TK1593 IST→FRA | TK1588 FRA→IST | U6774 IST→SVX
- Fastest acceptable: 100 505 RUB, elapsed 21h20, risk score 8 due below-ideal buffers.

## Where the time goes
- Original default-pool answer: 85 022 RUB / 43h50; main time loss is outbound overnight at IST: 17h40 wait after SVX→SVO→IST before IST→FRA.
- Expanded-pool best: 93 751 RUB / 23h40; removes the SVO detour and the IST overnight. Outbound becomes 8h45 with a 3h05 IST connection; return remains 14h55 with a 4h05 IST connection.
- Aggregate controls show cheaper one-way offers, but their displayed `duration` is flight-time, not total elapsed; return top also contains SAW→IST cross-airport transfer, so it is not automatically operationally better.

## Inconsistencies / algorithm complexities
- Default `candidate_pool_limit=5000` truncated the route universe: outbound_pairs=168, return_pairs=105, possible combos=17640, saved candidates=5000.
- Direct SVX→IST→FRA pairs existed but started at outbound-pair index 74; with 105 return pairs, the default pool can cover only about the first 47 outbound pair buckets. Result: one-stop options were excluded before full-route ranking.
- After rerun with `--candidate-pool-limit 20000`, CLI itself selected the one-stop 93 751 RUB / 23h40 option and stopped using two-stop fallback.
- Coverage diagnostics still say targeted coverage only: aggregate controls searched=2; several direct/carrier controls were planned/not_executed. This is bounded evidence, not proof of route absence.
- Provider aggregate candidates have unknown single-PNR/protection/baggage/fare rules. They are booking-screen candidates, not confirmed protected tickets.

## Direct controls
- SVX→FRA direct-only: 0 offers; raw variants filtered as non-direct=402
- FRA→SVX direct-only: 0 offers; raw variants filtered as non-direct=426

## Source boundaries
- Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.
- Kupibilet aggregate controls can reveal provider-assembled route offers, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.
- Travelpayouts/Aviasales cached absence is not negative evidence.
- Provider failures such as unavailable FLI MCP are source availability failures, not route absence evidence.
