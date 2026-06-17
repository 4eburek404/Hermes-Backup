---
name: flight-search
version: 0.5.0
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

4. Let the CLI manage static catalog freshness for catalog-dependent commands: by default it refreshes missing or older-than-2-weeks metadata before planning. Treat `data.catalog_auto_refresh` as runtime metadata, not flight evidence.
5. Read the final answer only from `data.agent_report.user_answer.rendered_text`.
6. Read `frontier.offer_graph` first, then `agent_guidance` for readiness/next actions, then use structured report fields for confidence checks before replying: `route.flow_decision`, `route.evidence_plan`, `evidence.coverage_diagnostics`, `evidence.provider_failures`, `evidence.source_boundaries`, `evidence.through_fare_checks`, `frontier.recommended_options`, and `frontier.priority_options`.

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
    "max_connections": null
  },
  "filters": {
    "only_carriers": []
  },
  "output": {"agent_brief": true}
}
```

For direct-only inventory set `route_options.max_connections` to `0`. For carrier scope fill `filters.only_carriers`.

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
3. **Mixing direct and connected options when direct flights exist.** When direct (T0\_DIRECT) flights are available, connected options (T1\_ONE\_STOP and above) are suppressed at the assembly level (`assembly.py:assemble_segment_results`) — not merely demoted by ranking. User requirement: direct exists → show ALL direct, no connected; no direct → one-stop fallback; connected when direct exist → only on explicit user request. Budget caps (`max_recommended_options=5`, `catalog limit=10`) must not truncate direct flights — when all ranked options are T0\_DIRECT, budget bypass fires. Round-trip: filter is per-direction — direct outbound + no direct return → direct×one-stop. See `references/debug-playbook.md` § "Direct vs Connected Mixing" for root causes and fix details.
4. Overclaiming single PNR, baggage-through, protection, fare rules, or terminal.
5. Silently widening named airports to city scope.
6. Rewriting, re-ranking, or copying raw diagnostic JSON instead of delivering the canonical rendered text.
7. Adding new audit/session/proposal Markdown files instead of moving durable behavior into CLI/report/tests or canonical references.
8. Re-adding old parameter names or keeping backward-compatibility shims. When a name changes (e.g. `fallback_max_connections` → `tier2_max_connections`), change it everywhere — code, CLI flags, JSON schemas, tests, docs — in one clean pass. **No legacy aliases, no `getattr(args, "old_name", None)` fallbacks, no `"old_name": still_accepted` in JSON schema enums.** Old names are dead; keeping them alive breeds confusion. The parameter is `tier2_max_connections`; for direct-only inventory set `max_connections` to `0`.
9. Using «fallback» in reference prose when the mechanism is a priority tier, deferred probe, or secondary tier. Use «deferred», «secondary tier», «two-stop tier», or «last-resort» instead. Moscow/SVO controls are first-class controls, not fallback-only behavior. The codebase rename is complete: all `fallback_*` identifiers are now `tier2_*`, `deferred_*`, `delegated_*`, `default_*`, or `secondary_*`.
10. **Prose-assertion tests that break on rephrasing.** Tests must verify deterministic code, not search for exact phrases in Markdown files. If an invariant is important enough to test, encode it in Python (`config.py` constants, `ProviderName` literal, `PREFERRED_AIRPORT_TIERS`, `RU_PRIORITY_BRANCHES`, `PROVIDER_REGISTRY`, dataclass fields) and write a code-level assertion against that structure. `assertIn("some English sentence", reference_text)` breaks every time prose is rephrased or deduplicated — replace it with a structural or code-level check. CLI paths and JSON wire-format field paths (`data.agent_report.user_answer.rendered_text`) are acceptable assertion targets because they are contract strings, not prose.
11. **Duplicating rules across reference files instead of cross-referencing.** When the same rule (airport priority, provider scope, city-code policy) appears in multiple `.md` files, keep one canonical source and replace the duplicates with a cross-reference sentence. Duplicates drift apart and create conflicting guidance.
12. **Bulk rename checklist (order matters):** (a) `grep -rn` for the old name across `flights_cli/`, `tests/`, `contracts/`, `references/`, `SKILL.md`. (b) Rename in Python code, CLI flags, JSON schemas, and test data in one pass. (c) Update test assertions that reference doc strings — if reference prose changed, the test must match the new wording, or better: replace prose-assertion with a code-level check. (d) Remove any files created as rename maps or migration notes; they are not canonical references. (e) Run `pytest tests/ -x` to catch missed schema keys, stale test strings, or cross-reference mismatches. (f) If a test asserts content from a reference file that was deduplicated (replaced by a cross-reference), move the assertion to the canonical file or replace it with a structural/code-level check.
13. **`is not None` guard for `max_connections_per_journey`.** When checking `int(o.get("max_connections_per_journey") or 0) == 0` to detect direct flights, options without the key (test fixtures, mock data) silently evaluate to `0` and look like direct flights. Always guard: `o.get("max_connections_per_journey") is not None and int(o.get("max_connections_per_journey")) == 0`. Without the guard, budget bypass fires on mock/test data that never set the field, breaking tests like `test_huge_report_is_bounded_and_records_omitted_counts`.
14. **Respect candidate-generation caps; expand only the displayed all-direct catalog.** `--max-candidates N` still bounds candidate generation and must not be bypassed. The all-direct expansion may raise the reporting/catalog limit (`include_ranked_candidates` default path) only when `all_direct_inventory` is true, and only up to `ALL_DIRECT_CATALOG_CAP`; this surfaces direct flights that survived assembly without mixing in connected options.
15. **All-direct catalog expansion uses a single source flag, not per-layer helpers.** The pipeline has three truncation layers that default to `limit=5`: (a) `assembly.py` — `include_ranked_candidates` default; (b) `agent_report_builder.py` — `ranked_candidate_options(data, limit=CATALOG_LIMIT_DEFAULT)`; (c) `agent_report_builder.py` — `build_itinerary_display(report, store, limit=…)`. When >5 direct flights exist, these layers silently drop options before budget bypasses can protect them. **Architecture:** a single `all_direct_inventory` flag is computed once in `assembly.py` from post-filter journeys (`outbound_is_direct and return_is_direct` with at least one real direct direction). The flag flows downstream via `ranked["assembly"]["all_direct_inventory"]`. Each truncation layer reads the flag and raises its limit to `min(len(items), ALL_DIRECT_CATALOG_CAP)` when true, instead of re-deriving "all direct?" from data shape. `ALL_DIRECT_CATALOG_CAP = 20` prevents unbounded output. `report_budget.py` and `user_answer.py` read `all_direct_inventory` from the internal `report["status"]["all_direct_inventory"]` (projected as `agent_report.frontier.status.all_direct_inventory`) instead of using their own `_all_options_direct()` / `_all_direct_options()` helpers. **Diagnosis:** run `diagnose kb-search ORIGIN DEST --direct-only --limit 20` — if all direct flights have prices in raw provider output but `display.options` shows fewer, the truncation is in the pipeline, not the provider. Check counts at each stage: `route_result.ranked` → `route_result.ranked_candidates` → `agent_report.frontier.recommended_options` and `agent_report.frontier.status.direct_omitted`. **Do not claim "provider did not return prices" when the display is truncated — always verify with `diagnose kb-search` first.** See `references/direct-priority-filter.md` § "Unified all_direct_inventory flag".

## Verification checklist

- [ ] Request scope normalized and encoded as `flight_search_request.v1`.
- [ ] Canonical command executed or the exact failing layer reported.
- [ ] Flow/evidence classes checked in structured report fields when decision-relevant.
- [ ] Final user-facing text comes from `data.agent_report.user_answer.rendered_text`.
- [ ] Ticketing/protection/baggage/terminal claims are proven or explicitly unproven.
- [ ] Freshness, missing evidence, provider failures, and source boundaries are reflected only when they change the decision.
- [ ] Maintenance work stays in source/runtime scope and creates no new active reference files by default.
- [ ] **Direct-flight completeness:** if the report shows fewer direct flights than expected, verify with `diagnose kb-search` before attributing to the provider. The `all_direct_inventory` flag (computed in `assembly.py` from post-filter journeys) controls catalog expansion at all three truncation layers. When the flag is `True`, each layer raises its limit to `min(len(items), ALL_DIRECT_CATALOG_CAP=20)` instead of the default 5. Check `assembly.all_direct_inventory`, `assembly.preferred_outbound_journey_count`, `route_result.ranked`, `route_result.ranked_candidates`, `agent_report.frontier.recommended_options`, and `agent_report.frontier.status.direct_omitted` counts to locate any residual truncation point.

## References

- `references/report-contract.md` — `agent_report.v2`, `flight_search_user_answer.v3`, read order, renderer contract, semantic validation.
- `references/source-boundaries.md` — evidence classes, absence taxonomy, ticketing/protection boundaries, cache/provider limits.
- `references/provider-aware-airport-priority.md` — SSOT for airport/provider priority and city-code dispatch.
- `references/debug-playbook.md` — targeted probes, route-family debugging, architecture coupling, Kupibilet field mapping, layover/elapsed penalty.
- `references/direct-date-window.md` — direct/nonstop inventory over bounded date windows.
- `references/cli-maintenance.md` — source/runtime governance, CLI/report/schema maintenance, reference lifecycle.
- `references/rail-rzd-live-pricing.md` — official RZD read-only comparison workflow.
- `references/flow-decision-router.md` — intent/market/evidence router and routing strategy classes.
- `references/direct-priority-filter.md` — direct-priority filter: suppress one-stop when direct exists, budget bypass for all-direct, round-trip per-direction logic.
