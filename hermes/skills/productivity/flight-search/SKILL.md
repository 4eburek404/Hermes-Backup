---
name: flight-search
version: 0.9.0
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find, compare, or diagnose live flight options through the bundled CLI. One adult, economy. Never books or claims final fare, baggage, protected transfer, or single PNR unless the provider/booking screen proves it.

## Canonical Run

Write a `flight_search_request.v1` JSON file and run:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request "$HOME/flight-search-request.json"
```

Use the rendered answer from `data.agent_report.user_answer.rendered_text` or `data.route_result.agent_report.user_answer.rendered_text`. Do not answer from raw provider JSON when the frontier/report is present.

Minimal request:

```json
{"schema_version":"flight_search_request.v1","origin":"ORIGIN","destination":"DEST","depart_date":"YYYY-MM-DD","profile":"business"}
```

Common options:

- Direct only: `"route_options":{"max_connections":0,"tier2_max_connections":0}`
- Date window: add `"date_window_end":"YYYY-MM-DD"` inside `route_options`; omit `return_date`.
- Return trip: `"return_date":"YYYY-MM-DD"`
- Hard constraints: `"constraints":{"must_include_airports":["AMS"],"first_departure_after":"15:00","only_carriers":["KL"]}`
- Soft carrier preference: `"constraints":{"preferred_carriers":["KL"]}`
- Provider override only when needed: `"provider_policy":"tutu"`, `"kupibilet"`, or `"fli"`

## Pipeline

Runtime flow:

```text
request
  -> normalize and validate flight_search_request.v1
  -> FlowDecision + EvidencePlan
  -> SearchPlanBuilder seeds constraints into provider probes
  -> per-probe provider router
  -> primary offer queries + bounded gateway waves
  -> OfferGraph
  -> DecisionScorer
  -> DecisionFrontier
  -> agent_report.v3 + user_answer.v6
```

There is no legacy assembly fallback. `RoutePlanBuilder`, old `services/assembly`, synthetic controls, and old `ranked_candidates/frontier_candidates` answer paths are not runtime sources.

## Providers

Provider routing is per probe, not per whole search.

- `tutu` is the default primary provider.
- In `auto`, a successful Tutu MCP probe stops fallback execution for the same logical probe.
- `kupibilet` is fallback only when Tutu is unavailable, fails, or does not support the probe and KupiBilet capability/market fit it.
- `fli` is fallback only for non-RU probes when Tutu is unavailable, fails, or does not support the probe.
- `provider_policy=both` is invalid.

Tutu returns shopping evidence. It can return connected offers and supports pagination through the adapter. Carrier names are resolved through localized airline catalogs into canonical carrier codes, not route-specific code.

When wave-0 primary offers prove direct flights for a direction, the direct-first gate suppresses connected options for that direction unless explicit route constraints override it.

## Constraints

User constraints are planner inputs before ranking:

- `must_include_airports` seeds gateway/path probes and rejects options without the required airport.
- `first_departure_after` applies to the first outbound departure in origin-local time; it does not filter return departures.
- `only_carriers` is hard; `preferred_carriers` is scoring preference.
- Carrier matching uses normalized codes and raw provider names.

If the user says "through AMS" or "KLM after 15:00", do not let default bridge policy outrank that request. Defaults live in policy/config and only fill gaps when the user did not constrain the route.

## Evidence Boundaries

Use report fields for evidence and absence language:

- Provider offers are shopping evidence, not booking proof.
- Empty provider output is not proof that no flight exists outside executed probes.
- Static catalogs, cached metadata, and diagnostics do not prove availability.
- Named airports are not city scope unless the request or report explicitly broadens scope.
- For round trips, frontier options are outbound+return pairs; unpaired directional evidence belongs in diagnostics.

Details: `references/report-contract.md`, `references/source-boundaries.md`, and `references/pipeline-reference.md`.

## Diagnostics

Use diagnostics to inspect the pipeline, not as traveler-facing answers:

```bash
python3 -m flights_cli --json diagnose plan --request "$HOME/flight-search-request.json"
python3 -m flights_cli --json diagnose probe --provider tutu --request "$HOME/probe.json"
python3 -m flights_cli --json diagnose tutu-search ORIGIN DEST --depart-date YYYY-MM-DD
```

For CLI/debug ownership and source boundaries, start from `references/index.md`.
