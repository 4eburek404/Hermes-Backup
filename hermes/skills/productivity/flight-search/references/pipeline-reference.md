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
| Request/options | `pipeline/options.py`, `pipeline/search_request.py` | Convert JSON/CLI fields into typed route, evidence, filter, and constraint options. |
| Flow decision | `pipeline/search_pipeline.py`, `pipeline/flow_decision.py`, `pipeline/evidence_plan.py` | Classify intent, market, provider policy, evidence requirements, freshness, and required controls. |
| Planning | `orchestrators/search_plan_builder.py` | Seed constraints into primary and gateway probes; produce diagnostics and an empty legacy segment fallback envelope. |
| Provider routing | `adapters/providers/registry.py` | Choose providers per probe by policy, market, and capability. Tutu is primary, KupiBilet fallback, FLI non-RU only. |
| Probe execution | `execution/offer_query_runner.py`, `execution/search_wave_planner.py`, `execution/gateway_leg_probe_executor.py`, `execution/aggregate_control_runner.py` | Execute bounded provider probes and record ledger evidence. |
| Graph/materialization | `pipeline/offer_graph.py` | Build provider-provenance edges and materialize N-leg/cross-day candidates. |
| Ranking/frontier | `pipeline/decision_scorer.py`, `pipeline/candidate_ranker.py` | Apply chronology, constraint, MCT, direct-first gate outcomes, round-trip pairing, and scoring policy. |
| Reporting | `services/agent_report.py`, `reporting/agent_report_builder.py`, `reporting/user_answer.py` | Project `agent_report.v3`, `flight_search_user_answer.v6`, and final traveler text from DecisionFrontier only. |

## Provider Policy

- `auto`: per-probe routing with Tutu first, KupiBilet fallback, FLI only where the probe is non-RU and supported.
- `tutu`, `kupibilet`, `fli`: force that provider where capability and market allow it.
- `both`: invalid.

Provider routing is never a whole-search exclusive lock in `auto`; each probe is routed independently.

## Constraints

Constraints are planner inputs and scorer gates:

- `must_include_airports` seeds gateway/path probes and rejects candidates missing the airport.
- `first_departure_after` filters first outbound departure before frontier selection.
- `only_carriers` is hard; `preferred_carriers` is soft scoring input.
- Carrier matching uses normalized codes and raw provider names.

## Chronology and MCT

Chronology applies to every edge and every round-trip pair. MCT applies only at cross-ticket boundaries. Provider-returned through-fare edges are provider-validated and only need chronological ordering inside the offer.

## Diagnostics

Use `diagnose plan` for planned probes, `diagnose probe --provider tutu|kupibilet|fli` for one provider probe, and `diagnose tutu-search` for Tutu-specific raw search diagnostics.
