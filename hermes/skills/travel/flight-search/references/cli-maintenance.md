# Flight Search CLI Maintenance

The CLI is an agent-facing implementation tool. Preserve deterministic stdout,
stable schemas, bounded provider execution, and explicit diagnostics.

## Source and runtime

Develop in the canonical Hermes-Backup checkout and its canonical development
environment. Source validation does not silently update the installed runtime
skill. When runtime sync is requested, prove source commit, runtime path,
version parity, and generated-artifact state separately.

The runtime is a standalone copy of the whole skill tree: its documented launch
runs `python3 -m flights_cli` from that copy's `cli/` directory. Publish one
source revision as a full-tree replacement, using the existing `git archive`
plus `rsync -a --delete` flow (or an equivalent remove-then-copy operation).
Overlay copies are unsupported because they retain deleted Python modules. Run
`maint check --runtime-path <published-skill-root>` afterward and require
source/runtime parity before making runtime claims.

## Public boundaries

- Input: `flight_search_request.v1` — the only accepted request version.
- Output: `flight_search_result.v1`.
- Canonical text: `data.rendered_text`.

There is no third public schema. The diagnostic trace and its schemas are gone:
a narrowed `search --request` is the diagnostic now.

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
  with the plan v6 schema.
- Provider execution and lifecycle: `execution/search_executor.py` and
  `execution/probe_ledger.py`.
- Connection/stop policy: `domain/connection_policy.py` and
  `domain/stop_policy.py`.
- Graph model/construction/materialization/merge: owning modules
  `pipeline/offer_graph_model.py`, `pipeline/offer_graph_builder.py`,
  `pipeline/offer_graph_materializer.py`, and `pipeline/offer_graph_merge.py`.
  Import graph symbols directly from their owning module; do not recreate a
  re-export façade.
- Candidate validation/scoring/frontier: `pipeline/candidate_outcome.py`,
  `pipeline/candidate_scoring.py`, and `pipeline/frontier_selection.py`.
- Public answer projection: `reporting/answer_options.py` (options),
  `reporting/evidence.py` (evidence), `reporting/answer_text.py` (rendered
  text), and `reporting/date_window_inventory.py` (per-date window status).
- Result assembly: `pipeline/result_builder.py`, which takes the request, the
  frontier options, the probe ledger, and the date window — and nothing else.

Projection and rendering cannot call providers, inspect cache/storage, rescore,
or alter frontier order. A segment carries IATA codes, offset-aware times,
carrier, and a nullable flight number, frozen before rendering.

## Required validation

Run targeted tests while changing a layer, then the full offline suite, Ruff,
format check, pyflakes, vulture, compileall, schema/resource checks, belief-map
boundaries, `maint doctor`, and `maint check`. The subprocess E2E must exercise
the real parser, planner, executor, graph, scorer, projection, schema/semantic
validators, and renderer against a local MCP stub.

For live acceptance, disable stale live cache, run the source CLI in the
canonical environment, inspect every probe terminal state and logical-query
dedupe, and never assert fixed prices or flight inventory.

## Runtime provenance

Before attributing behaviour to a provider or to the skill, prove which code
ran:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --version
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import flights_cli, pathlib; print(pathlib.Path(flights_cli.__file__).resolve())'
```

Record the source path, branch, and commit alongside the request that produced
the behaviour. `maint doctor` proves local readiness, never live inventory.
