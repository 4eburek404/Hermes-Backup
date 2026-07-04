# Provider-aware Airport Priority

Use this source reference when maintaining routing, provider dispatch, or report semantics for multi-airport city codes. Keep dated notes and temporary implementation context out of active prompt docs.

## Active provider scope

- The active provider set is Tutu MCP, KupiBilet, and FLI. In `auto`, Tutu MCP is primary; KupiBilet and FLI are fallback-only when Tutu is unavailable, fails, or does not support the logical probe.
- Static catalogs remain metadata only: they can normalize cities, airports, countries, airlines, alliances, and aircraft labels, but they do not prove live fares, availability, schedules, or direct service.

## Airport priority policy

This file is the single source of truth for airport/provider priority rules. Other docs may describe airport continuity as a source boundary, but should point here for city-code expansion and provider dispatch details.

- IST means the exact airport code `IST`; do not add `SAW` unless the user explicitly requests `SAW`.
- London defaults to business-priority airport tiers: LHR first; `LGW` as secondary tier only if `LHR` has no accepted/viable offers; `STN` and `LTN` excluded by default.
- Dubai city scope defaults to `DXB` primary. Use `DWC` as secondary when relevant; include `SHJ` only when the user asks for Sharjah, a Sharjah-based carrier, cheapest UAE-wide options, or a provider returns it and the report labels it.
- Moscow airports are not interchangeable for itinerary continuity; KupiBilet city-code behavior is covered below, and reports must still show actual `SVO`/`DME`/`VKO` airports.
- Keep preferred-tier and excluded-by-default metadata in the plan/report surface so ranking and audits can explain why one airport was preferred or suppressed.

## KupiBilet MOW city-code policy

- KupiBilet uses `MOW` city-code first.
- Exact `SVO`/`DME`/`VKO` deferred probes are not executed in parallel when city-code results have accepted offers.
- If the preferred airport tier has accepted/viable offers, lower-tier airport probes wait; for London this means `LGW` waits for `LHR` to produce no accepted/viable offers.
- Actual airports must be post-validated against `SVO`/`DME`/`VKO` and displayed as actual airport codes, not only `MOW`.
- Missing actual airport fields or out-of-scope actual airports must invalidate city-code results and allow exact-airport deferred probes.

## Tutu city-name policy

- Tutu `search_avia` receives Russian city names; the adapter resolves IATA code to city name before the MCP call.
- Exact-airport requests remain exact after normalization: offers whose actual first/last airports do not match the requested airport scope are skipped with `airport_scope`.
- City-code requests may accept any in-scope airport, but reports must still show actual airport codes.

## FLI exact-airport policy

- FLI is exact-airport only and must not receive `LON` city-code queries by default.
- For `IST→LON`, FLI candidates are `IST→LHR` first, then `IST→LGW` as secondary tier.
- Do not add `SAW`, `STN`, or `LTN` to default FLI probes.

## Smoke invariants

These provider-specific invariants can be proved with mocked/offline execution unless the question is live availability:

- KupiBilet: successful `SVX→MOW` skips exact deferred calls to `SVX→SVO`, `SVX→DME`, and `SVX→VKO`;
- FLI: successful `IST→LHR` skips secondary-tier calls to `IST→LGW`;
- default planning: `SAW`, `STN`, and `LTN` are absent unless requested or returned and accepted within scope.

## RU-priority and report contract

- `direct_destination_control` is a search branch, not a nonstop claim.
- RU-priority controls remain structural: branch visibility must link to structured `priority_options` fields such as `control_family`, `control_branch`, `visibility_role`, and `priority_option_id`.
- Moscow/SVO is a first-class control for Russian-origin international routes, not deferred-only behavior. Viable via-SVO controls must be coherent same-airport routes; rejected airport splices such as `SVO` vs `IST` are invalid itineraries.
- For domestic Russian routes, do not let profile scoring bury objectively better direct flights: if both airports are in Russia and direct domestic offers exist, the report/user answer must keep the cheapest/fastest direct option visible even if carrier weighting ranks a hub option higher.
- For carrier-specific existence questions, answer the carrier-route scope first and run targeted direct/carrier controls before saying the carrier does not fly the route.
- Semantic validation must use structured fields, not only `answer_lines`.
- Display/report output must show actual airport codes from normalized offers; city codes are request scope, not a substitute for actual departure/arrival airports.

## Maintenance cross-reference

Source/runtime sync and validation rules live in `references/cli-maintenance.md`; keep this file focused on provider and airport priority policy.
