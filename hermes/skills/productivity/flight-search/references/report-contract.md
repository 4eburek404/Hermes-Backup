# Flight Report Contract

Use this when reading `data.agent_report` or deciding what to show the user. Raw CLI internals are debug-only.

## Read Order

1. `display` - deterministic user-facing flight lines. Use `display.text` verbatim for itinerary text.
2. `answer_lines` - compact summary and critical warnings.
3. `recommended_options` - viable ranked options with segment details.
4. `priority_options` - controls that must stay visible even when lower-ranked.
5. `through_fare_checks` - routes that need airline/GDS/single-PNR verification.
6. `provider_failures` - unavailable provider evidence that must be named.
7. `source_boundaries` - caveats about source type and proof limits.
8. `hub_viability` / `rejected_pair_warnings` - explain missing or demoted routes only when useful.

## Detail Completeness

Do not present exact routing from a summary-only option. Any option named in `answer_lines`, `recommended_options`, or `priority_options` should carry `detail_status`:

- `full`: segments are present; safe to summarize.
- `summary_only`: price/time may be known, but segment details are incomplete.
- `missing`: do not infer the routing; rerun targeted debug.

`segment_results=[]` does not prove segment details are absent. Full route bodies can still live under `ranked_candidates[].candidate.journeys[].segments[]`. If the compact report clipped a cheaper, faster, direct, same-carrier, or Moscow-control option, escalate to debug instead of guessing.

## Recommendation Rules

Lead with `recommended_options[0]` only when it is viable, has `detail_status=full`, and no mandatory control materially changes the decision.

`agent_report.stop_policy_diagnostics.candidate_generation_mode` and `fallback_used` describe how assembly generated the candidate pool. Treat two-stop options as reportable only when fallback is explicitly active. Do not infer fallback mode from missing compact options or from aggregate controls alone.

Always surface materially different controls:

- cheapest acceptable when much cheaper;
- fastest acceptable when much faster;
- direct/nonstop controls;
- same-carrier or requested-carrier controls;
- Moscow/SVO controls for international routes from Russian origins when viable;
- airport-quality controls such as `LHR` for London business travel.

Explain lower ranking with concrete trade-offs: price, elapsed time, arrival time, airport quality, connection quality, ticketing/protection, or baggage.

## Route-Specific Decision Rules

Moscow/SVO is a first-class control for Russian-origin international routes, not a fallback. Show a viable via-SVO option even when a direct, IST/DXB, or other primary-hub option ranks better. The control must be a coherent same-airport route such as `origin -> SVO + SVO -> destination`; rejected `SVO vs IST` splices are invalid and should be explained as airport mismatches, not as viable itineraries.

For domestic Russian routes, do not let the `business` profile bury objectively better direct flights. If both airports are in Russia and direct domestic offers exist, lead with the cheapest/fastest direct option even when preferred-carrier scoring ranks an IST/SVO hub route higher. State that the business profile ranked the hub route higher because of carrier weighting, but the direct domestic route is cheaper/faster.

For SU-only or Aeroflot-only requests, use provider-assembled aggregate controls filtered by `SU` (`--aggregate-control-carrier SU`). Segment assembly can miss same-carrier through-PNR opportunities; aggregate controls may be the better evidence surface, but still require through-fare verification.

For a carrier-specific existence question, answer the carrier-route question first, then show alternatives. Run targeted direct/carrier controls before saying a carrier does not fly a route; `live-assemble` alone is not negative proof.

## Connection Trade-Offs

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons. Show them plainly as comfort/operations trade-offs. Keep real risk separate: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Answer Shape

Use this order:

1. Best viable recommendation.
2. `display.text` copied as-is for the itinerary. It already includes per-leg flight lines, layovers between legs, and total elapsed time including layovers.
3. Mandatory controls and material trade-offs.
4. Provider failures, if any.
5. Rejected/demoted warnings only when they explain the decision.
6. Purchase-screen verification caveats.

Never present summed separate-segment prices as confirmed airline/GDS through fares.
Never present `candidate_pool_limit` changes as a normal answer-quality strategy; missing preferred options are a CLI generation bug, not a reason to ask the user for a larger pool.
