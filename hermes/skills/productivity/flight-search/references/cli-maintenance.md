# Flight Search CLI Maintenance

The CLI is an agent-facing implementation tool. Preserve deterministic stdout,
stable schemas, bounded provider execution, and explicit diagnostics.

## Source and runtime

Develop in the canonical Hermes-Backup checkout and its canonical development
environment. Source validation does not silently update the installed runtime
skill. When runtime sync is requested, prove source commit, runtime path,
version parity, and generated-artifact state separately.

## Public boundaries

- Input: `flight_search_request.v3`.
- Output: `flight_search_result.v9`.
- Canonical text: `data.answer.rendered_text`.
- Diagnostic trace: `flight_route_trace_diagnostic.v4`.

JSON stdout is one envelope and one terminal newline. Text search stdout is the
validated rendered text only. Successful commands leave stderr empty. The JSON
serializer rejects non-finite numbers; the input reader rejects duplicate keys.

Schema defaults are documentation only; Python normalizes and applies defaults
once in `search_request_from_payload`. Use the packaged local schema registry for `$ref`
resolution. Do not add public schemas for internal evidence, decision, cache, or
CLI envelope types.

## Change ownership

- Request/defaults: `pipeline/search_request.py`.
- Production composition root: `orchestrators/search_workflow.py`.
- Planning: `orchestrators/search_plan_builder.py` and `pipeline/search_plan.py`
  with the plan v5 schema.
- Provider execution and lifecycle: `execution/search_executor.py` and
  `execution/probe_ledger.py`.
- Connection/stop policy: `domain/connection_policy.py` and
  `domain/stop_policy.py`.
- Graph construction/materialization/merge: dedicated
  `pipeline/offer_graph_*` modules; `pipeline/offer_graph.py` is a façade.
- Candidate validation/scoring/frontier: `pipeline/candidate_validation.py`,
  `pipeline/candidate_scoring.py`, and `pipeline/frontier_selection.py`;
  `pipeline/candidate_ranker.py` is a façade.
- Coverage, catalog semantics/projection/rendering: their dedicated modules in
  `reporting/`.
- Result projection: `pipeline/result_builder.py`.

Projection and rendering cannot call providers, inspect cache/storage, rescore,
or alter frontier order. A catalog segment freezes IATA, offset-aware times,
carrier, nullable flight number, terminals, equipment, duration, and layover
facts before rendering.

## Required validation

Run targeted tests while changing a layer, then the full offline suite, Ruff,
format check, pyflakes, vulture, compileall, schema/resource checks, belief-map
boundaries, `maint doctor`, and `maint check`. The subprocess E2E must exercise
the real parser, planner, executor, graph, scorer, projection, schema/semantic
validators, and renderer against a local MCP stub.

For live acceptance, disable stale live cache, run the source CLI in the
canonical environment, inspect every probe terminal state and logical-query
dedupe, and never assert fixed prices or flight inventory.
