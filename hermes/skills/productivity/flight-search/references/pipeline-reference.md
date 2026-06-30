# Flight-search Pipeline Reference

Current data-flow map for the bundled `flights_cli` package. Use this when maintaining or debugging how a `flight_search_request.v1` becomes a `flight_search_result.v1` and `data.agent_report.user_answer.rendered_text`.

For the reference owner map, start with `references/index.md`. This file owns pipeline mechanics; it does not own traveler caveat wording (`source-boundaries.md`) or targeted live probes (`debug-playbook.md`).

## 1. Layers

| Layer | Modules | Responsibility |
|---|---|---|
| CLI/input | `cli.py`, `command_surface.py`, `apps/search.py`, `commands/` | Parse commands, read request JSON, emit JSON envelopes. |
| Request pipeline | `pipeline/search_request.py`, `pipeline/flow_decision.py`, `pipeline/evidence_plan.py` | Normalize request, classify intent/market/evidence, choose routing/provider/evidence policy. |
| Planning | `pipeline/search_plan.py`, `orchestrators/search_plan_builder.py`, `orchestrators/route_plan_builder.py`, `domain/` | Build `SearchPlan` diagnostics; keep the legacy `RoutePlanBuilder` focused on segment fallback planning, route families, airport tiers, date windows, and hub logic. |
| Execution | `orchestrators/live_assembly_runner.py`, `execution/` | Run segment probes through provider ports, dedupe, ledger, cache/failure states. |
| Providers | `ports/`, `adapters/providers/`, `providers/` | KupiBilet and FLI adapters, normalized offers, capability boundaries. |
| Assembly/ranking | `services/assembly.py`, `services/ranking.py` | Direct/pair journeys, stop-policy buckets, candidate generation, ranking. |
| Reporting | `reporting/`, `services/agent_report.py`, `services/agent_report_contract.py` | Flat report, user-answer v3, budget, nested projection, schema/semantic validation. |
| Contracts/state | `contracts/`, `store.py`, `io.py`, `output.py` | JSON schemas, static catalog/store, output helpers. |

Active provider set: `kupibilet` and `fli` via `adapters/providers/registry.py`. Static catalogs are metadata only; they never prove live flights.

## 2. Input and output contracts

**Input**: `flight_search_request.v1` (`contracts/flight_search_request.v1.schema.json`). Important fields:

- top-level: `origin`, `destination`, `depart_date`, optional `return_date`, `currency`, `profile`, `ticketing`, `provider_policy`;
- `route_options`: routing strategy, hubs/airports, `max_connections`, `tier2_max_connections`, date window, stop policy;
- `evidence`: probe budget, cache/freshness flags, aggregate controls, sidecar URLs;
- `filters`: carrier include/exclude/prefer/avoid;
- `output`: output and diagnostic limits.

`apps/search.py::live_assembly_options_from_search_request` validates the schema and materializes defaults into `LiveAssemblyOptions`. The downstream request pipeline reads typed `SearchRequest`, `FlowDecision`, and `EvidencePlan` fields; it does not depend on argparse-style compatibility dicts.

**Output**: `flight_search_result.v1` from `apps/search.py::build_search_result`:

- `request` — normalized request;
- `agent_report` — nested `agent_report.v2`; final answer path is `data.agent_report.user_answer.rendered_text`;
- `route_result` — full route/assembly debug payload including `live_search`.

## 3. Main flow

```text
request JSON
  → normalize/validate search request
  → build LiveRouteSearchFlow: FlowDecision + EvidencePlan
  → SearchPlanBuilder exposes diagnostic SearchPlan
  → RoutePlanBuilder builds the current segment fallback plan
  → LiveAssemblyRunner dispatches segment probes through provider adapters
  → assemble_segment_results builds journeys/candidates/ranking
  → aggregate controls and date-window inventory attach extra evidence
  → build_agent_report builds flat report
  → build_user_answer builds user_answer.v3 and rendered_text
  → apply_agent_report_budget trims debug-heavy fields
  → project_agent_report builds nested agent_report.v2
  → validate_agent_report validates schema + semantic rules
  → flight_search_result.v1 envelope
```

`--json` stdout must contain the JSON envelope; provider logs/warnings belong on stderr or structured fields.

## 4. Flow decision and evidence plan

`pipeline/flow_decision.py::decide_flow` classifies before provider or command reasoning:

| Axis | Values | Notes |
|---|---|---|
| `intent_class` | `route_recommendation`, `direct_inventory`, `ticketing_proof`, `carrier_or_airport_scope`, `maintenance` | Direct inventory is triggered by strict direct-only thresholds. Carrier/exact-airport scope must be answered before alternatives. |
| `market_class` | `ru_domestic`, `ru_touching_international`, `global_non_ru`, `structurally_constrained` | Computed from catalog country metadata, not ad-hoc code lists. |
| `evidence_class` | `shopping_advisory`, `absence_claim`, `ticketing_required`, `diagnostic_only` | Absence/ticketing classes require stronger controls and freshness. |
| `routing_strategy` | `domestic-ru`, `ru-priority`, `hub-list`, explicit strategies | Global non-RU must not silently inherit RU-priority/Moscow controls. |

`pipeline/evidence_plan.py::plan_evidence` derives:

- required controls: direct/exact-airport, date-window direct, Moscow gateway, carrier aggregate, full-route aggregate;
- freshness/cache policy: absence/ticketing/no-cache/near-departure disables live cache;
- provider policy: `auto` routes RU-touching segments to KupiBilet and non-RU segments to FLI unless overridden;
- `agent_guidance`: canonical command, answer path, readiness, blocking evidence, and request-patch next actions.

## 5. Segment planning and provider dispatch

`RoutePlanBuilder` is currently the **segment fallback planner**, not the universal search planner. It creates `plan["segments"]` with direction, leg, date, origin, destination, route family, priority metadata, airport-tier metadata, and skip hints.

Primary full-route offers, including provider aggregate/through-fare searches, are represented in `SearchPlan.primary_offer_queries` when the selected provider supports full-route aggregate collection. These queries are diagnostic-only for now: `LiveAssemblyRunner` does not execute them, and the existing legacy `plan` artifact remains the execution source for fallback segment probes until provider execution is migrated.

Do not treat provider aggregate collection as exhaustive coverage for `ru_to_western_europe_bridge`; keep segment fallback coverage active for that bridge route family.

Key planning rules:

- Direct inventory/date-window requests expand direct legs by date window and stay strict direct-only.
- RU-touching international can add RU-priority controls: direct destination, IST primary, and Moscow gateway. Secondary fallback gateways belong to data-driven gateway discovery, not imperative segment generation.
- Domestic-RU stays domestic: direct exact-airport controls first, no international hubs by default.
- City-code-first provider behavior and airport tiers are owned by `provider-aware-airport-priority.md`.
- `direct_route_intel` can skip unsupported SVX direct-control pairs when official route intelligence is available; unavailability is reported as a boundary, not as live absence.

Provider dispatch (`adapters/providers/registry.py`):

| `provider_policy` | Segment provider set |
|---|---|
| `kupibilet` | KupiBilet only |
| `fli` | FLI only |
| `both` | KupiBilet + FLI |
| `auto` + RU-touching segment | KupiBilet |
| `auto` + non-RU segment | FLI |

Provider adapters return typed `ProviderProbeResult` values. Unsupported probes must be structured `not_supported` results so reports can distinguish source capability boundaries from missing evidence.

## 6. Probe execution and ledger

`LiveAssemblyRunner` executes the plan:

1. Build `LiveRouteSearchFlow`, diagnostic `SearchPlan`, and the executable segment fallback plan.
2. Reject requests whose planned segment count exceeds `evidence_plan.max_segment_searches`.
3. Run skip predicates before dispatch: direct-route-intel negative, preferred airport tier already has offers, city-code primary already has offers, direct probe already has offers, better priority route already viable.
4. Dispatch eligible segment probes via `execution/probe_dispatcher.py` and provider adapters.
5. Record every planned/searched/skipped/failed/not-supported/deduped control in `ProbeExecutionLedger`.
6. Synthesize missing Moscow gateway summaries when RU-priority controls need structured reporting.
7. Build date-window inventory, run aggregate controls, finalize unexecuted controls.

Ledger projection is the source of `evidence.coverage_diagnostics`. Planned-but-not-terminal controls mean execution is incomplete; `not_supported` is a terminal source boundary and should be surfaced only when decision-relevant.

## 7. Provider normalization

Providers normalize raw offers to a common offer shape. The canonical list of flights/legs inside a normalized offer is `segments`.

Rules:

- Do not reintroduce `flights` as a fallback key for normalized offers. Raw provider responses may use provider-specific names; adapters must normalize them before assembly.
- KupiBilet flight numbers are normalized by `providers/kupibilet.py::kupibilet_flight_number`; if the raw number already contains the carrier prefix, the duplicate prefix is stripped.
- Provider-specific raw bodies and URLs are diagnostics; they are not final-answer input.

## 8. Assembly, stop policy, and direct priority

`services/assembly.py::assemble_segment_results` receives normalized `segment_results`.

Current assembly sequence:

1. Build one-stop pairs separately for outbound and return with connection/airport checks.
2. Build direct journeys for outbound and return.
3. Apply **direct-priority per direction**:

```python
outbound_journeys = outbound_direct if outbound_direct else outbound_pairs
return_journeys = return_direct if return_direct else return_pairs
```

If direct journeys exist for one direction, one-stop pairs for that direction are suppressed. The directions are independent: a round trip can be direct outbound and one-stop return when only the outbound direction has direct journeys.

4. Compute `all_direct_inventory` once from the post-filter journeys:

```python
outbound_is_direct = bool(outbound_direct) or not outbound_journeys
return_is_direct = bool(return_direct) or not return_journeys
all_direct_inventory = (
    (bool(outbound_direct) or bool(return_direct))
    and outbound_is_direct
    and return_is_direct
)
```

5. Split journeys by stop policy.
6. Generate candidates from preferred journeys first. If none exist, include the configured secondary tier (`tier2`) and set `tier2_used=True`.
7. Dedupe, rank, attach diagnostics, and cap debug-heavy candidate lists.

Stop-policy thresholds:

| Policy | preferred | secondary tier | hard max | Notes |
|---|---:|---:|---:|---|
| `business-default` / `allow-two-stop-tier` | 1 | 2 | 2 | One-stop preferred; two-stop only when no preferred candidate exists. |
| `strict-direct-one-stop` | 1 | 1 | 1 | No two-stop tier. |
| `debug-all` | 2 | 99 | 99 | Diagnostics only; can expose garbage options. |

Strict direct-only request intent is `max_connections == 0` and `tier2_max_connections == 0`; it is independent of the stop-policy name.

## 9. All-direct output propagation

`all_direct_inventory` prevents direct flights from being hidden by output caps. A provider result from a `direct_outbound`/`direct_return` query is direct inventory only when the actual offer journey has one segment; connected offers returned by a direct-route provider query remain one-stop options.

Current propagation:

1. `assembly.py` writes `ranked["assembly"]["all_direct_inventory"]` and direct-priority counters.
2. `agent_report_builder.py` reads `data["assembly"]`, sets flat `report["status"]["all_direct_inventory"]`, and computes `direct_omitted` using `ALL_DIRECT_CATALOG_CAP`.
3. `report_budget.py` reads `report["status"]["all_direct_inventory"]` and does not trim `recommended_options` when the displayed set is all direct.
4. `user_answer.py` reads `agent_report["status"]["all_direct_inventory"]` while building the v3 catalog.
5. `project_agent_report` nests the status and user answer into public `agent_report.v2`.

Diagnosis for “direct flights missing from display” lives in `debug-playbook.md`; first verify provider raw direct evidence with a narrow direct probe before blaming provider absence.

## 10. Reporting projection

`reporting/agent_report_builder.py::build_agent_report` builds a **flat** report first:

- `route`: route, dates, profile, provider policy, `flow_decision`, `evidence_plan`;
- `status`: counts, direct-priority flags, all-direct flag, omissions;
- evidence fields: source boundaries, segment searches, provider failures, aggregate controls, coverage diagnostics, stop policy, through-fare checks, rejected pair warnings, direct flights;
- frontier inputs: `recommended_options`, `priority_options`, `offer_graph`;
- diagnostics before canonical rendering: display fragments and answer lines;
- `user_answer`: canonical `flight_search_user_answer.v3` with `rendered_text`;
- diagnostics after canonical rendering: `human_answer` mirror copied from `user_answer.rendered_text`.

Then:

1. `apply_agent_report_budget` trims debug-heavy lists and records `omitted_counts`.
2. `project_agent_report` converts flat report to nested `agent_report.v2`: `route / evidence / frontier / user_answer / agent_guidance / diagnostics`.
3. `services/agent_report.py::attach_agent_report` validates nested report against schema and semantic rules. Schema failures are `CliError(contract_error)`, not silent field drops.

`diagnostics.human_answer.text` is mirror-only diagnostic output: it must mirror `user_answer.rendered_text` while it exists and must not render or fallback independently.

## 11. Data artifact map

| Artifact | Shape | Owner |
|---|---|---|
| `request` | normalized request dict | `apps/search.py`, `pipeline/search_request.py` |
| `args` | materialized `argparse.Namespace` | `apps/search.py` |
| `FlowDecision` / `EvidencePlan` | typed frozen decisions | `pipeline/` |
| `SearchPlan` | diagnostic search plan: primary offer queries, mandatory controls, gateway discovery, fallback segment plan | `SearchPlanBuilder` |
| `plan` | executable segment fallback plan plus route/evidence metadata | `RoutePlanBuilder` |
| `segment_results[]` | normalized provider offers with `segments[]` | provider adapters + execution |
| `assembled` | ranked candidates, assembly diagnostics, live_search | `services/assembly.py`, `LiveAssemblyRunner` |
| flat `report` | report builder working shape | `agent_report_builder.py` |
| nested `agent_report` | public `agent_report.v2` | `agent_report_projector.py`, schema |
| `result` | public `flight_search_result.v1` envelope | `apps/search.py` |

## 12. Maintenance command map

These are maintenance/diagnostic surfaces, not normal traveler answers:

- `search --request` — primary production search.
- `diagnose plan --request` — segment plan only, no provider calls.
- `diagnose probe` — one provider probe from JSON.
- `diagnose render` — render diagnostics from an existing report.
- `diagnose kb-search` / `diagnose kb-roundtrip` — narrow KupiBilet controls.
- `diagnose fli-search` / `diagnose fli-dates` — narrow FLI controls.
- `route validate|rank|assemble` — offline/development stages.
- `maint check`, `maint doctor`, `maint catalog manifest|refresh` — readiness, source/runtime, static catalog maintenance.

Do not use provider-specific diagnostics as the primary search path unless `search --request` is degraded and a narrower proof is needed.
