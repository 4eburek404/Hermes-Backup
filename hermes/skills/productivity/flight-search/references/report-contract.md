# Flight Report Contract

Use this reference when `data.agent_report` is unclear. The report is the normal agent-facing output; raw CLI internals are debug-only.

## Read Order

1. `answer_lines` — compact summary suitable for first-pass reasoning.
2. `recommended_options` — best ranked viable options with segments, price, elapsed time, risk, and connections.
3. `priority_options` — mandatory controls that must be shown or considered even if they rank lower.
4. `through_fare_checks` — airline/GDS/single-PNR verification required before treating a route as a through fare.
5. `provider_failures` — failed provider calls that must be named, especially FLI MCP outages.
6. `source_boundaries` — caveats about provider type and what the source cannot prove.
7. `hub_viability` and `rejected_pair_warnings` — use only to explain missing or demoted options.

## Recommended Options

Use `recommended_options[0]` as the main recommendation only when `ok=true` and no `priority_options` or `through_fare_checks` materially changes the recommendation.

State:
- total route and dates;
- price and currency;
- segments with flight numbers and local times;
- connection minutes and risk grade;
- ticketing/protection caveat.

## Priority Options

Treat these as mandatory controls, not optional clutter. Show them when they materially affect trust or decision quality.

Common categories:
- `all_su_svo`: all-Aeroflot via SVO. Important for Russia/Asia routes and possible single-PNR pricing.
- `svo_hub`: Moscow/SVO control, even if IST/DXB ranks higher.
- `all_su`: all-Aeroflot control, even outside SVO.
- `single_carrier`: same-carrier multi-leg route that may have through-fare implications.
- direct/nonstop controls when live aggregate finds a direct flight outside assembled one-stop ranking.
- airport-quality controls such as `LHR` for London business trips.

If a priority option is worse, say why: higher price, longer elapsed time, worse arrival, or less convenient schedule. Do not omit it solely because it is below top-N.

For routes where the destination geography is Asia/China/Oceania, SVO controls are mandatory. An IST/DXB mixed-carrier option can still be the best recommendation, but all-SU/SVO must be visible when viable.

## Through-Fare Checks

When present, state that segment assembly cannot price or prove airline/GDS through fares. Verify with:
- airline website;
- GDS/Sirena/Amadeus-capable seller;
- booking-screen fare rules, baggage, and protection.

Do not present a segment-sum price as the final through-fare price.

## Provider Failures

If present, say which provider failed and on which leg. Do not silently replace
failed FLI/MCP evidence with Kupibilet aggregate results. A provider failure is
source unavailability, not proof that no flight or route exists.

## Answer Shape

Use this order:

1. Best recommendation.
2. Mandatory controls and trade-offs.
3. Provider failures, if any.
4. Rejected/demoted warnings only if useful.
5. Verification caveats before purchase.

## Demotion Language

Use concise trade-off language:

- "Lower-ranked because it is more expensive."
- "Lower-ranked because elapsed time is longer."
- "Cleaner carrier/ticketing control, but verify through fare before using the segment-sum price."
- "Operationally worse due to airport change, tight buffer, overnight layover, or low-cost/leisure carrier risk."
