# Agent Report v2 Migration Notes

Use this when continuing the flight-search CLI/report refactor from a flat `agent_report.v1` contract to a layered `agent_report.v2` contract.

## Target shape

Production serialized report should be a thin wrapper:

```text
agent_report.v2
  ├─ route
  ├─ evidence
  │   ├─ coverage_diagnostics
  │   ├─ provider_failures
  │   ├─ source_boundaries
  │   ├─ through_fare_checks
  │   └─ probe/control ledger fields
  ├─ frontier
  │   ├─ status
  │   ├─ offer_graph
  │   ├─ recommended_options
  │   └─ priority_options
  ├─ user_answer
  │   └─ rendered_text
  └─ diagnostics
      ├─ display
      ├─ answer_lines
      └─ human_answer
```

Legacy top-level fields such as `recommended_options`, `priority_options`, `answer_lines`, `display`, `human_answer`, `offer_graph`, `coverage_diagnostics`, `provider_failures`, and `source_boundaries` should not remain required or serialized as top-level production contract fields.

## Migration pattern that worked

1. Write RED tests against serialized production output, not only in-process dict access:
   - `schema_version == "agent_report.v2"`;
   - top-level required fields are `route`, `evidence`, `frontier`, `user_answer`, `diagnostics`;
   - legacy top-level fields are absent from serialized report;
   - `user_answer.rendered_text` remains canonical final output.
2. Create a small v2 adapter/wrapper rather than copying v1 into several schemas.
3. Keep a temporary in-process legacy view only for internal migration:
   - semantic validators and render fallbacks can read aliases through `legacy_agent_report_view()`;
   - JSON output/tests for public contracts must use the v2 nested paths directly.
4. Move old field families by layer:
   - evidence/source/probe/completeness data → `evidence`;
   - recommendation/frontier/priority data → `frontier`;
   - deterministic final answer → `user_answer`;
   - debug/display/legacy projections → `diagnostics`.
5. Update tests that assert public CLI JSON to nested v2 paths, not legacy aliases:
   - `report["frontier"]["recommended_options"]` instead of `report["recommended_options"]`;
   - `report["frontier"]["priority_options"]` instead of `report["priority_options"]`;
   - `report["diagnostics"]["answer_lines"]` instead of `report["answer_lines"]`;
   - `report["evidence"]["source_boundaries"]` instead of `report["source_boundaries"]`.
6. Keep legacy alias support only as a migration aid for Python internals; do not let alias support mask public contract regressions.

## Validation gates

Run focused tests first, then the full suite:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_agent_report_contract.py \
  tests/test_final_answer_contract.py \
  tests/test_human_answer_renderer.py \
  tests/test_agent_report_budget.py \
  tests/test_route_workflows.py \
  -q

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest tests -q

git diff --check
```

If full suite fails on `KeyError` for legacy top-level fields, first decide whether the test is asserting public serialized output or internal compatibility:

- public serialized output: migrate the test to v2 nested paths;
- internal migration compatibility: use the legacy view explicitly.

## Pitfalls

- Do not solve v2 by copying the entire v1 schema into `evidence`, `frontier`, and `diagnostics`; that preserves the overload.
- Do not keep `human_answer.text` as canonical. It is a legacy projection/fallback and should mirror `user_answer.rendered_text` only while both exist.
- Do not let `--agent-brief`, `--agent-report`, or `--agent-mode` change search semantics while refactoring schemas; they should remain output/budget presets or thin compatibility wrappers.
- Avoid broadening the public flag matrix while internals are still overloaded. Finish evidence/frontier/user-answer separation first.
