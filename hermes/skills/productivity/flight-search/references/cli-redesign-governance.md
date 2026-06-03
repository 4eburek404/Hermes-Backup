# CLI Redesign Governance

Use this reference when redesigning or auditing the flight-search CLI/report path after a session where the user asks for architectural simplification rather than a one-off route search.

## Core Lesson

Do not treat “agent mode” as a single design primitive. In the current CLI it conflates three concerns:

1. **Report attachment** — whether to attach structured `agent_report` / debug details.
2. **Output shape** — normal human/prose JSON versus compact machine-readable payload.
3. **Evidence budget** — whether to spend extra provider/control budget.

Do **not** solve that by adding a public taxonomy of modes/flags (`none`, `user`, `agent`, `debug`, `human`, `json`, `--format`, `--report`, `--evidence`) unless there is a concrete user-facing need. That recreates the same Babel-tower problem under cleaner names. Keep the public command thin and boring; use internal resolver concepts only where they reduce code coupling. Output/report flags must not secretly start more provider calls; extra provider work belongs to the planning/probe layer, not to `--agent-*` output wrappers.

## Agent Flag Migration Target

Current behavior to preserve during migration:

- `--agent-report`: thin wrapper; attach/validate `data.agent_report` without changing search budget.
- `--agent-brief`: compact agent JSON output; should not mutate evidence budget after refactor.
- `--agent-mode`: overloaded compatibility preset; currently enables report, compacts output, and may set `aggregate_control_limit=10`.

Target compatibility posture:

- `--agent-report`: thin wrapper; attach/validate `data.agent_report` without changing search budget or renderer semantics.
- `--agent-brief`: compact report payload; implies report attachment only, and must not mutate evidence budget or legacy `agent_mode`.
- `--agent-mode`: explicitly legacy compatibility preset only; if kept, it may preserve old compact-output/top-ranked/aggregate-control defaults, but do not design new behavior around it.

Migration rule:

- Prefer removing/parking confusing public flags over mapping them into a larger public matrix.
- If internal code needs names like report/output/evidence intent, keep them internal to parser/resolver tests.
- Do not expose JSON-for-humans/debug-for-users modes without a specific consumer and contract.
- The future public path should converge on one `flights search`/`route live-assemble` flow with request flags for route constraints, not meta-flags about “agentness”.

## Schema Redesign Rule

`agent_report.v1` is a catch-all contract. A large nested-required count means the schema is requiring fields across many layers, not just at top level. Treat that as a maintenance-risk signal.

Preferred cutover:

- `common.v2.schema.json` — route, price, segment, provider/source/cache/error primitives.
- `search_evidence.v2.schema.json` — probe intents, terminal states, provider failures, source exhaustion, budget expiry, completeness.
- `offer_frontier.v2.schema.json` — recommended options, alternatives, cheapest/fastest/direct/frontier representatives, decision stability, missing evidence.
- `flight_search_user_answer.v2.schema.json` — canonical user answer.
- `agent_report.v2.schema.json` — wrapper around evidence/frontier/user_answer/diagnostics.

Avoid permanent v1/v2 dual support. If a migration branch temporarily carries v1 and v2, include a cleanup gate before merge: production builders emit only the new schema; v1 remains only in explicit legacy fixtures/tests or is removed.

## Canonical User Answer Rule

Do not maintain parallel final-prose sources. The desired flow is:

```text
frontier + evidence + stop_policy
  -> build_user_answer(...)
  -> validate_user_answer(...)
  -> render_human(user_answer)
  -> optional agent_report.user_answer
```

`human_answer`, `answer_lines`, and `display` may exist only as projections/fallback/debug artifacts, not independent semantic sources. The user-facing contract must be integrated into the main pipeline, not built as a side contract used only by tests.

Architectural fork rule: do not settle for a "minimal safe" patch that leaves ambiguous source-of-truth behavior. The durable solution is a single canonical user-answer contract with rendered text, validation in the report validator, and legacy projections forced to mirror it until schema cutover.

Staged migration rule for the current `agent_report.v1` codebase:

1. Add `agent_report["user_answer"]` as a runtime field produced by the report builder.
2. Require `user_answer.rendered_text` and derive `user_answer.answer_lines` from it, not from diagnostic `agent_report.answer_lines`.
3. Validate it with `flight_search_user_answer.v1` contract tests and from `validate_agent_report(...)`; map nested errors under `$.user_answer...`.
4. Make human rendering prefer `user_answer.rendered_text` over `human_answer`, `display`, and `answer_lines`.
5. Keep legacy `human_answer`/`display`/`answer_lines` until the schema cutover because `agent_report.v1` currently requires them, but make `human_answer.text` mirror `user_answer.rendered_text` and fail validation if it diverges.
6. Only after the v2 cutover, remove or demote the legacy fields to diagnostics/projections.

Do not make the first step a destructive removal of v1-required fields; that creates avoidable schema churn instead of reducing duplication. Do not leave multiple renderer sources live after the migration step; that just moves the overload from flags into schemas.

## Provider Port Rule

Do not remove the provider port abstraction. Complete it:

- registry returns concrete provider adapters implementing `FlightProviderPort`;
- segment and aggregate probes both dispatch through provider adapters;
- provider-specific cache, normalization, summaries, source boundaries, and error mapping live inside adapters;
- common output is `ProviderProbeResult`, projected into evidence/frontier contracts.

Direct `if provider == "kupibilet"` / `elif provider == "fli"` dispatch in core execution is a migration target, not the final design.

## Aggregate Controls Rule

Carrier/full-route aggregate controls should be `ProbeIntent`s in the same ledger path as segment probes. Avoid separate mini-dispatchers for aggregate controls. Required terminal states include `searched`, `failed`, `skipped`, `not_supported`, `deduped`, `budget_expired`, and `source_exhausted`.

## Stop Policy Contract Rule

Stop policy belongs in contracts, not optional prose. Always include compact stop-policy status in `user_answer`/frontier/report. Detailed diagnostics belong to debug report level, not a confusing public flag such as `--include-stop-policy-diagnostics`.

Useful contract fields:

- policy name and preferred/fallback/hard max connections;
- whether two-stop fallback is allowed/used;
- three-plus suppressed count;
- garbage/options suppressed count;
- per-option `stop_tier`, `max_connections_per_journey`, `reportable_by_stop_policy`, and reason.

## Workflow Preference

For major redesigns, write a plan file first, then execute in small validated commits:

1. provenance/source-runtime decision;
2. RED tests for intent/schema/output rules;
3. implementation for one coherent layer that resolves the architectural source of truth, not just the smallest compatible patch;
4. focused validation;
5. commit;
6. continue to the next layer.

If the user challenges a plan as a flag/schema “Babel tower” or rejects a “minimal safe” fork, treat that as a design constraint: reduce public surface area and finish the canonical data-flow for the layer under work before moving on. Do not do a broad breaking rewrite without intermediate validation and cleanup gates.
