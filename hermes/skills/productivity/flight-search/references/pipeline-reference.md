# Flight Search Pipeline Reference

The runtime path is frontier-first. It does not fall back to the removed segment assembly runtime.

## Flow

```text
flight_search_request.v1
  -> apps.search.normalize_search_request
  -> pipeline.search_pipeline.build_live_route_search_flow
  -> orchestrators.search_plan_builder.build_search_plan
  -> execution.offer_query_runner.run_primary_offer_queries
  -> execution.search_wave_planner.SearchWavePlanner
  -> pipeline.offer_graph.build_offer_graph
  -> pipeline.decision_scorer.DecisionScorer
  -> reporting.agent_report_builder.build_agent_report
  -> reporting.user_answer.build_user_answer
```

## Ownership

| Layer | Owner | Responsibility |
| --- | --- | --- |
| Request/options | `pipeline/options.py`, `pipeline/search_request.py` | Convert JSON/CLI fields into typed route, evidence, filter, and output options. |
| Flow decision | `pipeline/search_pipeline.py`, `pipeline/flow_decision.py`, `pipeline/evidence_plan.py` | Classify intent, market, provider policy, evidence requirements, freshness, and required controls. |
| Planning | `orchestrators/search_plan_builder.py` | Build primary and gateway probes from route, evidence, and filters; produce search-plan diagnostics and planned provider work. |
| Provider routing | `adapters/providers/registry.py` | Choose providers per probe by policy, market, and capability. Tutu is primary; KupiBilet and FLI are fallback-only when Tutu is unavailable, fails, or does not support the probe. |
| Probe execution | `execution/offer_query_runner.py`, `execution/search_wave_planner.py`, `execution/gateway_leg_probe_executor.py`, `execution/aggregate_control_runner.py` | Execute bounded provider probes and record ledger evidence. |
| Graph/materialization | `pipeline/offer_graph.py` | Build provider-provenance edges and materialize N-leg/cross-day candidates. |
| Ranking/frontier | `pipeline/decision_scorer.py`, `pipeline/candidate_ranker.py` | Apply chronology, MCT, direct-first gate outcomes, round-trip pairing, and scoring policy. |
| Reporting | `services/agent_report.py`, `reporting/agent_report_builder.py`, `reporting/user_answer.py` | Assemble compact `agent_report.v5`, `flight_search_user_answer.v7`, and final traveler text from DecisionFrontier only. |

## Provider Policy

- `auto`: per-probe routing with Tutu MCP first. A searched Tutu result short-circuits fallback providers for the same logical probe; KupiBilet and FLI run only when Tutu is unavailable, fails, or does not support the probe.
- `tutu`, `kupibilet`, `fli`: force that provider where capability and market allow it.
- `both`: invalid.

Provider routing is never a whole-search exclusive lock in `auto`; the Tutu-first short-circuit is scoped to each logical probe.

Tutu MCP facts:

- endpoint: `https://mcp.tutu.ru/mcp` by default, overridden by `FLIGHTS_TUTU_MCP_URL`;
- tool: `search_avia`, JSON-RPC over Streamable HTTP;
- input: Russian city names, not IATA codes; the adapter resolves IATA through `Store.city_by_code`;
- output: shopping offers, not booking or purchase proof;
- capabilities: RU-touching and global markets, segment and full-route aggregate probes, direct-only and carrier post-filtering, carrier aggregate, round-trip input, and cache;
- pagination: `TUTU_PAGE_SIZE = 30`, `TUTU_MAX_PAGES = 3`, `sort=departure_asc`, with `pages_fetched`, `has_more_after_fetch`, and `not_fetched_due_to_page_budget` metadata.

Tutu normalization extracts IATA from parenthesized airport strings, resolves carrier display names through localized airline catalogs (`airlines_en.json` and `airlines_ru.json`) where possible, maps `segments_count - 1` to connection count, and keeps provider-returned round-trip outbound/return journeys instead of flattening them into fake one-way connections. Carrier filtering must use normalized carrier identity, not depend on `voyage_no` or flight-number prefixes being present.

## Airport and Provider Scope

City codes describe request scope; normalized offers and reports must show actual airport codes.

- Exact airport requests stay exact unless the user allows city scope.
- Tutu searches by city name, then post-filters exact-airport requests against normalized first/last airports; mismatches are skipped with `airport_scope`.
- KupiBilet uses `MOW` city-code first; exact `SVO`/`DME`/`VKO` deferred probes are not executed in parallel when city-code results have accepted offers.
- FLI is exact-airport only and must not receive `LON` city-code queries by default.
- IST means exact `IST`; do not add `SAW` unless requested.
- London defaults to `LHR` first, with `LGW` secondary only if `LHR` has no accepted/viable offers; `STN` and `LTN` are excluded by default.
- Dubai city scope defaults to `DXB`; use `DWC` as secondary when relevant; include `SHJ` only when requested, carrier-relevant, cheapest UAE-wide, or provider-returned and labeled.
- Moscow airports are not interchangeable for itinerary continuity; reports must show actual `SVO`/`DME`/`VKO` airports.

RU-priority controls remain structured report fields, not prose-only rules: `direct_destination_control` is a search branch, not a nonstop claim; Moscow/SVO is a first-class control for Russian-origin international routes; domestic-RU direct offers must stay visible when they are objectively cheapest/fastest even if profile scoring ranks a hub option higher.

## Gateway Policy

Gateway selection is policy/config driven, not route-specific Python branching.

- Default bridge hints may seed gateway discovery through route policy/config.
- Provider-returned full-route offers can add gateway evidence through gateway discovery.
- Coverage controls are evaluated from existing graph evidence before spending provider budget.
- Route-specific provider data belongs in fixtures, policy/config, or live provider evidence, not hardcoded origin/destination/carrier branches.

## Direct-First Gate

After wave-0 primary offer queries, `LiveAssemblyRunner` computes direct evidence per direction. If direct evidence is present and route options do not explicitly allow connected alternatives, that direction enters `direct_mode`.

- `direct_mode` skips gateway leg probes for that direction with ledger reason `direct_mode`.
- Connected primary paths for a `direct_mode` direction are rejected with `direct_mode_gate`.
- Explicit `route_options.max_connections >= 1` disables the gate because the request allows connected alternatives.
- If direct options exist but no acceptable candidate remains, one fallback wave may run with hard cap one connection; this does not apply to routes with no direct evidence.

## Filters

Carrier filters are provider-query inputs:

- `filters.only_carriers` narrows provider/search queries where supported.
- `filters.prefer_carriers` is a provider-query preference and RU-priority seed; it is not a hidden scorer gate.
- Carrier matching uses normalized codes and raw provider names.

## Direct Date Window

Use request-level date windows when the user asks for all direct/nonstop flights over several dates. This is inventory, not a route-recommendation frontier.

```json
{
  "schema_version": "flight_search_request.v1",
  "origin": "ORIGIN",
  "destination": "DEST",
  "depart_date": "YYYY-MM-DD",
  "profile": "business",
  "provider_policy": "auto",
  "route_options": {
    "max_connections": 0,
    "tier2_max_connections": 0,
    "date_window_end": "YYYY-MM-DD"
  },
  "output": {"catalog_limit": 10, "direct_catalog_limit": 30}
}
```

`depart_date` is the inclusive start; `route_options.date_window_end` is the inclusive end. Do not pass a `--date-window-end` CLI flag. Date-window mode requires strict direct-only route options and no `return_date`; the CLI fails fast otherwise. Read per-date inventory from `date_window_inventory`, and summarize direct-offer dates before no-offer dates and source boundaries.

## Chronology and MCT

Chronology applies to every edge and every round-trip pair. MCT applies only at cross-ticket boundaries. Provider-returned through-fare edges are provider-validated and only need chronological ordering inside the offer.

## Diagnostics

Use `diagnose plan` for planned probes, `diagnose trace --request` for the full assembled route/live-search trace, and `diagnose probe --provider tutu|kupibilet|fli` for one explicit provider probe. Provider-specific raw-search commands are not part of the CLI surface.
