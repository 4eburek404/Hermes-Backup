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
- `--agent-brief`: compact report payload; implies report attachment only, and must not mutate evidence budget, search controls, stop-policy controls, or legacy `agent_mode`.
- `--agent-mode`: explicitly legacy compatibility preset only; if kept, it may preserve old compact-output/top-ranked/aggregate-control defaults, but do not design new behavior around it.

Migration rule:

- Prefer removing/parking confusing public flags over mapping them into a larger public matrix.
- If internal code needs names like report/output/evidence intent, keep them internal to parser/resolver tests.
- Do not expose JSON-for-humans/debug-for-users modes without a specific consumer and contract.
- The future public path should converge on one `flights search`/`route live-assemble` flow with request flags for route constraints, not meta-flags about “agentness”.

### Flag Audit Checklist

When the user asks to re-review the plan/skill/CLI, do not only continue implementation. First audit the current parser, command builders, schema builders, and tests for public-surface simplification opportunities:

- Which flags are real route/search constraints and can be embedded into canonical commands or presets?
- Which flags are only wrappers around output shape/report attachment (`agent`, `brief`, `report`) and should remain thin compatibility aliases or be parked for removal?
- Which flags unexpectedly change search semantics or budget? Move those semantics into internal request/probe/budget contracts; output/report flags must not do provider work.
- Do compact-output flags override explicit evidence/search controls such as `--stop-policy debug-all`, carrier controls, aggregate-control settings, or coverage controls? If yes, fix the flag helper so output trimming is reactive only; add RED tests around the exact parser/helper path.
- Which arguments are unused, only threaded for future plans, or duplicated under multiple names? Remove or explicitly mark as legacy with tests before adding new flags.
- Which commands/modules implement separate copies of the same flow (segment probes, aggregate controls, city-pair controls, provider dispatch, provider summaries)? Centralize them behind a single intent/ledger/provider-port path before adding features.

## Schema Redesign Rule

`agent_report.v1` is a catch-all contract. A large nested-required count means the schema is requiring fields across many layers, not just at top level. Treat that as a maintenance-risk signal. When reworking the agent path, explicitly compare agent-facing and user-facing schemas: if the user-answer schema carries probe ledger/debug/provider-internal detail, or the agent report owns final prose semantics, the boundary is overloaded.

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

Direct `if provider == "kupibilet"` / `elif provider == "fli"` dispatch in core execution is a migration target, not the final design. During audits, search for provider-specific algorithms that look similar but live in different modules: request normalization, cache lookup, error taxonomy, source-boundary wording, representative selection, and summary projection should be adapter/shared-helper code rather than command-local copies.

## Aggregate Controls Rule

Carrier/full-route aggregate controls should be `ProbeIntent`s in the same ledger path as segment probes. Avoid separate mini-dispatchers for aggregate controls. Required terminal states include `searched`, `failed`, `skipped`, `not_supported`, `deduped`, `budget_expired`, and `source_exhausted`.

For current `agent_report.v1` work, treat this as an end-to-end contract, not just a model refactor:

1. Runtime planning creates `ProbeIntent`s for every actually attempted or deliberately skipped segment/aggregate control; city-pair controls that are in scope but not executable must still be planned and finalized by the ledger.
2. Dispatch writes terminal evidence into one `ProbeExecutionLedger`: normal provider output → `searched`; `CliError`/provider failure → `failed`; provider capability boundary → `not_supported`; duplicate request → `deduped`; planned but not reached → `not_executed`.
3. `coverage_projector` may consume `live["probe_ledger"]`, fill missing buckets, and compute fallback completeness, but must not rebuild `planned_controls` or `not_executed_controls` from `plan["coverage_controls"]` when runtime ledger exists.
4. `not_supported_controls` is a canonical bucket: add it to the JSON schema, semantic validator, report-budget trimming, and fixtures/tests together. A schema-only addition is not enough because semantic validation may still accept stale reports.
5. Focused tests should cover segment, aggregate, and city-pair projections plus the negative case that an empty runtime ledger does not get post-hoc planned/not-executed controls from the static plan.

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

### Follow-up Plan After a Refactor

When the user asks “what is the plan then?” after a completed or partially completed architectural refactor, do not answer from conversation memory alone. First gather read-only provenance and code evidence, then produce a contract-closure plan rather than another abstract redesign:

1. verify source path, branch/HEAD/status, and whether the active release/runtime skill is separate from source;
2. inspect the actual implementation points for the refactored layer, especially runtime intent models, ledgers, projectors, schema/validator/report-budget code, and focused tests;
3. run the smallest relevant baseline suite before planning, so the plan names what is already green;
4. save the plan under `.hermes/plans/` with path, bytes, and SHA-256 in the final reply;
5. frame the next work as closing one data-flow contract end-to-end (for example `ProbeIntent -> ProbeExecutionLedger -> live.probe_ledger -> coverage_projector -> schema/validator/report_budget -> offer_graph/user_answer`), not as broadening the public flag/schema surface;
6. include explicit RED tests for negative cases where reporting must not recreate runtime state post-hoc;
7. keep runtime sync as a separate approval-gated side effect with backup, dry-run, parity check, and runtime smoke tests.
