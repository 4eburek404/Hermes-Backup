# Flight Search CLI Maintenance

The CLI is an agent-facing implementation tool. Preserve deterministic stdout,
stable schemas, bounded provider execution, and explicit diagnostics.

## Source and runtime

Develop in the canonical Hermes-Backup checkout and its canonical development
environment. Source validation does not silently update the installed runtime
skill. When runtime sync is requested, prove source commit, runtime path,
version parity, and generated-artifact state separately.

## Public boundaries

- Input: `flight_search_request.v1`.
- Output: `flight_search_result.v6`.
- Canonical text: `data.answer.rendered_text`.
- Diagnostic trace: `flight_route_trace_diagnostic.v2`.

JSON stdout is one envelope and one terminal newline. Text search stdout is the
validated rendered text only. Successful commands leave stderr empty. The JSON
serializer rejects non-finite numbers; the input reader rejects duplicate keys.

Schema defaults are documentation only; Python applies defaults once in
`SearchRequest.from_payload`. Use the packaged local schema registry for `$ref`
resolution. Do not add public schemas for internal evidence, decision, cache, or
CLI envelope types.

## Change ownership

- Request/defaults: `pipeline/search_request.py`.
- Planning: `orchestrators/search_plan_builder.py` and plan v2 schema.
- Provider execution and ledger: `execution/`.
- Graph/scoring/frontier: `pipeline/offer_graph.py`,
  `pipeline/decision_scorer.py`, and `pipeline/candidate_ranker.py`.
- Result projection: `pipeline/result_builder.py`.
- Structured answer/render: `reporting/user_answer*.py`.

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
