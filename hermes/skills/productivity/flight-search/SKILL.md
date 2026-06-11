---
name: flight-search
version: 0.11.0
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

## Use when

- Live flight search or route comparison.
- Direct/nonstop inventory for a date or bounded date window.
- Carrier-specific or exact-airport availability.
- Ticketing/protection/baggage risk checks; this skill never books tickets.
- Bounded train-vs-flight comparison after a flight search.
- Maintenance only when the user asks to inspect, debug, modify, or sync this skill, CLI, schemas, or report contract.

## Golden Path

1. Normalize route/date/scope: exact airports vs city scope, carrier, direct-only, return date, baggage/ticketing intent, and profile (`balanced` default).
2. Write a `flight_search_request.v1` JSON request.
3. Run the canonical search command from the skill CLI:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request /tmp/flight-search-request.json
```

4. Read the final answer only from `data.agent_report.user_answer.rendered_text`.
5. Read `frontier.offer_graph` first, then use structured report fields for confidence checks before replying: `route.flow_decision`, `route.evidence_plan`, `evidence.coverage_diagnostics`, `evidence.provider_failures`, `evidence.source_boundaries`, `evidence.through_fare_checks`, `frontier.recommended_options`, and `frontier.priority_options`.

## Request template

```json
{
  "schema_version": "flight_search_request.v1",
  "origin": "ORIGIN",
  "destination": "DEST",
  "depart_date": "YYYY-MM-DD",
  "return_date": null,
  "currency": "RUB",
  "profile": "balanced",
  "ticketing": "separate",
  "provider_policy": "auto",
  "route_options": {
    "max_connections": null,
    "fallback_max_connections": null
  },
  "filters": {
    "only_carriers": []
  },
  "output": {"agent_brief": true}
}
```

For direct-only inventory set both `route_options.max_connections` and `route_options.fallback_max_connections` to `0`. For carrier scope fill `filters.only_carriers`.

## Follow-up trigger map

Start with `search --request`; use follow-ups only when the report says evidence is missing or the user asks for a narrower proof.

- Direct/date-window inventory: direct-only request options; for a bounded window set `route_options.date_window_end` and read `evidence.date_window_inventory` (`references/direct-date-window.md`).
- Carrier or exact-airport scope: answer the requested scope first, then alternatives; required controls should appear in the report evidence plan.
- Single PNR, through baggage, protected connection, final fare, refund/exchange, or terminal certainty: require purchase-screen, airline/GDS, seller, or explicit upstream proof; otherwise say unproven.
- RU domestic: expect domestic-RU route mode and direct domestic visibility.
- RU-touching international: RU-priority/Moscow controls may be relevant; the report should record why.
- Global non-RU: must not silently inherit RU-priority, Moscow/SVO controls, or Russian-provider assumptions; if it does, treat it as a structured limitation.
- Train comparison after a flight search: use `references/rail-rzd-live-pricing.md` and keep the comparison bounded to price/time evidence.
- Maintenance/debug/refactor: use `references/cli-maintenance.md` and `references/debug-playbook.md`; do not expose maintenance output as the traveler answer.

## Source-boundary caveats

Keep caveats compact and source-bound:

- Live provider output is shopping evidence, not booking proof; recheck before purchase.
- Empty provider output is not structural absence unless targeted controls or structural route evidence support it.
- Static catalogs only normalize metadata: city/airport/country/airline data; they do not prove availability or schedules.
- Exact airports are not interchangeable; airport/provider priority policy lives in `references/provider-aware-airport-priority.md`.
- Cache freshness, required controls, skipped/failed/not-supported controls, provider failures, and missing evidence should come from structured report fields, not prompt-only reasoning.

## Common pitfalls

1. Using cached fare helpers, static catalogs, or maintenance diagnostics as availability evidence.
2. Starting with provider-specific probes instead of the canonical `search --request` path.
3. Treating direct inventory as route recommendation and adding connected options unasked.
4. Overclaiming single PNR, baggage-through, protection, fare rules, terminal, or final price.
5. Silently widening named airports to city scope.
6. Rewriting, re-ranking, or copying raw diagnostic JSON instead of delivering the canonical rendered text.
7. Adding new audit/session/proposal Markdown files instead of moving durable behavior into CLI/report/tests or canonical references.

## Verification checklist

- [ ] Request scope normalized and encoded as `flight_search_request.v1`.
- [ ] Canonical command executed or the exact failing layer reported.
- [ ] Flow/evidence classes checked in structured report fields when decision-relevant.
- [ ] Final user-facing text comes from `data.agent_report.user_answer.rendered_text`.
- [ ] Ticketing/protection/baggage/terminal claims are proven or explicitly unproven.
- [ ] Freshness, missing evidence, provider failures, and source boundaries are reflected only when they change the decision.
- [ ] Maintenance work stays in source/runtime scope and creates no new active reference files by default.

## References

- `references/report-contract.md` — `agent_report.v2`, `flight_search_user_answer.v3`, read order, renderer contract, semantic validation.
- `references/source-boundaries.md` — evidence classes, absence taxonomy, ticketing/protection boundaries, cache/provider limits.
- `references/provider-aware-airport-priority.md` — SSOT for airport/provider priority and city-code dispatch.
- `references/debug-playbook.md` — targeted probes and route-family debugging.
- `references/direct-date-window.md` — direct/nonstop inventory over bounded date windows.
- `references/cli-maintenance.md` — source/runtime governance, CLI/report/schema maintenance, reference lifecycle.
- `references/rail-rzd-live-pricing.md` — official RZD read-only comparison workflow.
- `references/flow-decision-router.md` — intent/market/evidence router and routing strategy classes.
