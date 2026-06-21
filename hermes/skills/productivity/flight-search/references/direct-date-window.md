# Direct Date-Window Flight Inventory

Use this reference when the user asks for all direct/nonstop flights over a bounded date range, e.g. “все прямые на неделе 22.06–28.06”. This is an inventory task, not a route-recommendation task.

## Trigger

- “все прямые”, “только прямые”, “nonstop/direct only” plus a date range/window.
- User asks availability/schedule for a direct service across multiple days.
- User wants “all direct” rather than cheapest/best connected routing.

## Canonical workflow

The per-date probe loop is executed by the CLI planner, not by the agent. Encode the window in the canonical request and run the Golden Path command once:

```json
{
  "schema_version": "flight_search_request.v1",
  "origin": "ORIGIN",
  "destination": "DEST",
  "depart_date": "YYYY-MM-DD",
  "profile": "balanced",
  "provider_policy": "auto",
  "route_options": {
    "max_connections": 0,
    "tier2_max_connections": 0,
    "date_window_end": "YYYY-MM-DD"
  },
  "output": {"agent_brief": true}
}
```

Semantics:

- `depart_date` is the window start; `route_options.date_window_end` is the inclusive window end (bounded; the CLI rejects windows longer than its `MAX_DATE_WINDOW_DAYS` limit).
- The window requires strict direct-only route options and no `return_date`; the request fails fast otherwise.
- The planner expands the window into per-date direct probe intents through the probe ledger; provider dispatch follows the normal policy (KupiBilet for RU-touching segments, FLI for non-RU/global segments under `auto`).
- Set `evidence.no_live_cache` when freshness matters or when validating the process.

## Reading the result

- Read per-date inventory from `data.agent_report.evidence.date_window_inventory.dates[]`: each entry carries `date`, `status` (`direct_offers`, `no_direct_offers`, `no_direct_offers_with_failures`, `probe_failed`, `not_probed`), `offer_count`, compact `offers[]` (carrier, flight number, local departure/arrival, price/currency), failed-probe counts, and skip reasons.
- Per-date planned/searched/failed/not-executed probe states stay visible in `evidence.coverage_diagnostics`.
- Summarize by date: dates with direct offers (flight, carrier, local times with `+1` when crossing midnight, price), then dates with no direct live offers, then the provider/source boundary and booking-screen checks.

For narrow debugging of a single suspicious date, the targeted `diagnose kb-search --direct-only` / `diagnose fli-search --direct-only` probes from `references/debug-playbook.md` remain available; they are debug evidence, not the canonical path.

## Boundaries and pitfalls

- A date-window direct inventory is not a recommendation frontier. Do not lead with connecting routes unless the user asks for alternatives.
- `evidence.date_window_inventory` is provider-live evidence (`boundary: provider_live_only`). Empty output for a date means the selected live provider returned no direct offer for that date; state that boundary plainly. Do not escalate to airline-site, airport-site, or schedule-aggregator checks unless the user explicitly asks for corroboration outside the provider-live scope.
- Do not split the answer into schedule vs shopping/purchase layers by default; the operational source of truth is provider-live direct-only evidence from the CLI.
- Keep time zones explicit enough to avoid duration mistakes: elapsed time comes from ISO offsets; show local airport times in the user answer.
