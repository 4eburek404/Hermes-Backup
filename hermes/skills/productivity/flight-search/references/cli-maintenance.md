# CLI Maintenance Notes

Use this when modifying or auditing the flight-search CLI, provider layers, route-family logic, coverage controls, report contract, skill Markdown, or source/runtime sync. Keep maintenance behind the `SKILL.md` maintenance gate; ordinary route search should stay traveler-facing.

## Workflow

- Start with provenance: runtime path, source path, branch, HEAD, dirty state, version markers, and whether runtime is intentionally ahead of source.
- Before any maintenance/refactor implementation, compare source and runtime with generated-artifact excludes. If runtime is newer or semantically different, preserve/merge runtime guidance into source before `rsync --delete`.
- Work offline by default unless live provider access is the subject of the task.
- For behavior changes, add/update a focused failing test before implementation.
- Test parser/subprocess CLI contract and internal helpers. A test that instantiates `argparse.Namespace` does not prove the CLI accepts the flag.
- Preserve `--json --agent-brief` as JSON-clean stdout.
- Keep search behavior limited to current live provider assembly and documented targeted probes.
- Static catalogs are metadata only; flight options come from live provider assembly.
- If validation is interrupted, report the last completed gate and the missing gate; do not report completion.

## JSON stdout/stderr Rules

- In `--json` mode, stdout must contain only the JSON envelope.
- Diagnostics, warnings, and provider logs belong on stderr or inside structured JSON fields.
- Do not print secrets, full credential paths, or unredacted provider URLs with sensitive query data.
- If an error occurs, return the standard JSON error envelope with a concrete layer and actionable detail.

## Source, Runtime, and Mirror Validation

Current source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state lives under `$HERMES_HOME/skills/productivity/flight-search` (usually `$HOME/.hermes/skills/productivity/flight-search`) and is a separate deployment/sync surface. The active Hermes release path may intentionally exclude this runtime/user skill. The legacy distribution mirror `cli/skill-clis/flights` must not be recreated.

Before saying which version is current, run the compact local maintenance report when the CLI is available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maintenance check
```

Then check separately when deeper evidence is required:

- runtime skill `SKILL.md` version, bytes, and SHA-256;
- runtime CLI markers: `cli/pyproject.toml`, `cli/flights_cli/__init__.py`, and `python3 -m flights_cli --version` from runtime `cli/`;
- active Hermes release: whether `~/.hermes/hermes-agent/skills/productivity/flight-search` exists;
- local source checkout: `/home/konstantin/src/Hermes-Backup/hermes`, branch, HEAD, dirty state, and ahead/behind status;
- GitHub publication state only when asked for published link/current remote version.

If runtime is newer than source/GitHub, say so explicitly: operationally loaded runtime may be ahead of published source until source changes are committed and pushed.

## Runtime-to-Source Gate Before Publishing

Use this when the user asks to “sync with runtime” before committing or pushing a flight-search change. Treat runtime as an explicit input surface, not as a cache to overwrite blindly.

1. Verify source repo branch, `HEAD`, dirty status, origin URL, and whether the feature branch already has an upstream.
2. Compare runtime and source with generated-artifact excludes. Under `set -euo pipefail`, wrap `diff -qr ... | wc -l` as `(diff -qr ... || true) | wc -l`; otherwise a real diff can abort provenance commands.
3. Inspect changed runtime files before copying. If runtime has task-relevant docs/contract changes, sync runtime -> source with `rsync -a --delete` plus excludes for `__pycache__/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
4. Validate source/runtime parity after sync, run focused contract/doc tests and the full offline suite when the change touches `agent_report`, report contract, or user-facing decision logic.
5. Clean generated artifacts created by tests before staging.
6. Stage only the runtime-sync files that changed, run `git diff --cached --check` and an allowlist guard, commit the sync if needed, then push and verify local/remote SHA equality.

## Source-to-Runtime Gate

Use this gate after source docs or CLI changes and before touching runtime:

1. Verify source provenance: branch, HEAD, status, and expected target diff.
2. Verify version markers in `SKILL.md`, `cli/pyproject.toml`, and `cli/flights_cli/__init__.py` when version is in scope.
3. Run focused source tests before sync. Include schema/contract tests when `agent_report` behavior changes, and provider/airport policy tests when dispatch rules change.
4. Back up the runtime skill before every sync. Keep backups outside the active skill loader tree.
5. Compare source and runtime before overwriting. If runtime has semantic, non-generated changes absent from source, show the concise diff and ask whether to overwrite runtime, preserve it via source, or leave runtime intentionally ahead.
6. Dry-run `rsync -a --delete --itemize-changes` with generated-artifact excludes; validate deletion paths are intended.
7. Sync with excludes: `__pycache__/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
8. Validate source/runtime parity with the same excludes, then run key-file checksums for marker/config files when requested.
9. Run runtime checks after sync from runtime `cli/`: `python3 -m flights_cli --json doctor`, help/contract smoke for touched commands, and targeted offline tests when available.
10. Clean only generated runtime artifacts created by validation and rerun parity.
11. Do not restart the Hermes gateway unless explicitly authorized. Use a new Hermes session/reset only when cached skill text must refresh.

## Contract Registry and Lifecycle

Current public contracts:

- `agent_report.v2` — serialized report envelope with `route`, `evidence`, `frontier`, `user_answer`, `diagnostics`.
- `flight_search_user_answer.v3` — canonical user-facing answer contract; `rendered_text` is deterministic renderer output.

Retired legacy/projection surfaces:

- `flight_search_user_answer.v2` is rejected; there is no v2→v3 runtime adapter.
- `diagnostics.human_answer`, `diagnostics.display`, and `diagnostics.answer_lines` are debug/mirror projections only, not canonical final-prose sources and not fallback inputs.
- In-process legacy alias views are removed; consumers must read nested `agent_report.v2` paths.

Removed/shadow/proposed lifecycle:

- `common.v2`, `search_evidence.v2`, and `offer_frontier.v2` are not packaged active schemas.
- `agent_report.v1`, `flight_search_user_answer.v1`, and `flight_search_user_answer.v2` are not packaged active schemas.
- `flight_search_final_answer.v1` and `route live-answer` are proposed-only until schema, builder, command path, and exactness regression tests exist. Do not document them as Golden Path commands.

Schema/report changes must update, in one change: schema contract, report-building code, docs that tell agents how to read fields, fixtures/tests, and focused contract tests. Public JSON tests should assert nested v2 paths such as `report["frontier"]["recommended_options"]`, not top-level legacy aliases.

## CLI Surface and Contract Simplification

Use this when the user asks whether flags, schemas, commands, or agent/user paths are redundant, overloaded, or becoming a “свалка”. Separate three concerns before removals:

1. Search/evidence semantics — provider calls, probes, coverage controls.
2. Decision semantics — assembly, ranking, stop policy, frontier.
3. Output semantics — JSON size, `agent_report`, `human_answer`, brief rendering.

Rules:

- Do not treat “agent mode” as one design primitive. It can conflate report attachment, output shape, and evidence budget.
- Do not solve overload by adding a larger public taxonomy (`none/user/agent/debug/human/json`, `--format`, `--report`, `--evidence`) without a concrete consumer and contract.
- `--agent-report` should be a thin wrapper that attaches/validates `data.agent_report` without changing search budget.
- `--agent-brief` should trim output only; if it implies legacy `agent_mode`, call out inherited evidence/budget side effects in audits and tests.
- `--agent-mode` is a legacy compatibility preset, not a new design surface.
- Keep ordinary user commands narrow. Hide or classify as advanced/debug the knobs for candidate pool limits, raw/ranked/rejected bodies, live-cache TTL, direct-route-intel TTL, fail-fast, day-offset fanout, coverage-control internals, and aggregate-control internals.
- Prefer one public route-search wrapper over parallel user-facing variants. Provider-specific commands and offline `route plan/validate/rank/assemble` are diagnostics/development surfaces unless the user explicitly asks for provider-level proof.
- If `route kb-assemble` remains, document or implement it as a compatibility alias for `route live-assemble --provider-policy kupibilet`.

## Provider Port Rule

Do not remove the provider port abstraction. Complete it:

- `ports/providers.py` owns `FlightProviderPort`, `ProviderCapabilities`, `ProviderProbeResult`, provider/probe/evidence/cache literals.
- `adapters/providers/registry.py` returns concrete provider adapters, not only descriptors.
- provider adapters own cached search calls, normalization, post-validation, summaries, source boundaries, and error mapping.
- `execution/probe_dispatcher.py` loops over provider adapters and translates `ProviderProbeResult` into probe ledger/outcome types.
- aggregate controls call provider adapter `search_aggregate(...)` or receive structured `not_supported`; they must not contain provider-only algorithm branches.

Pitfalls:

- After moving direct calls out of `execution/`, update tests to patch adapter seams; do not re-export old symbols just to keep tests green.
- Avoid a registry that stores capabilities/descriptors while separate code constructs adapters elsewhere.
- If a provider cannot support aggregate probes, return structured `not_supported` so reports explain the source boundary instead of silently skipping it.
- Preserve dedupe and fail-fast semantics in the dispatcher adapter bridge; these are execution semantics, not provider-specific behavior.

## Provider and Airport Policy Coupling

The durable source contract lives in `references/provider-aware-airport-priority.md`. Keep implementation, tests, and docs aligned with these invariants:

- Active provider paths are KupiBilet and FLI; static catalogs are metadata only.
- `IST` is exact-airport `IST` by default; `SAW` requires explicit user request.
- London defaults to `LHR` first, with `LGW` deferred until `LHR` has no accepted/viable offers; `STN` and `LTN` are excluded by default.
- KupiBilet handles Moscow as `MOW` city-code first; exact `SVO`/`DME`/`VKO` fallback is deferred and must not run in parallel when city-code request has accepted offers.
- FLI is exact-airport only and must not receive city-code `LON` by default.
- City-code results must be post-validated against actual airport scope, and reports must display actual airport codes rather than only request city codes.

## Route-Family and Coverage-Control Rules

- Route-family metadata and segment-spec identity belong in shared route-graph helpers, not duplicated in docs, dry planners, or live planners.
- Keep RU domestic, RU-touching international, global non-RU, Asia/Oceania, and structurally constrained route logic consistent across public builders.
- Domestic-RU routing must be decided in one shared layer and propagated through `route plan`, assembly, and `route live-assemble`.
- For domestic Russian round trips, assert the direct return segment `DEST -> ORIGIN` and absence of default international hubs unless explicitly requested.
- Moscow/SVO controls are first-class controls when relevant, not fallback-only behavior.
- Coverage and aggregate-control flags must compile to a common `ProbeIntent`/evidence-goal model with provider capability and terminal status.
- `not_executed_controls` and `failed_controls` are missing/degraded evidence. `not_supported_controls` is a terminal provider/source capability boundary; it should be surfaced only when decision-relevant and must not make coverage incomplete by itself.

## Skill-to-CLI Promotion Rules

Use this when operational logic in `SKILL.md` starts compensating for deterministic CLI behavior. Prefer moving repeatable decision mechanics into the CLI/report contract rather than relying on agent prose.

- Promote behavior, not wording: encode constraints, controls, evidence, stop reasons, and frontier roles as structured report fields; keep final prose in the renderer.
- Treat the target architecture as constraints → executable evidence plan → progressive probes/polls → first-class offer graph → decision frontier/report.
- Move `ProbeExecutionLedger`-style state into execution/scheduling when it affects search completeness. Reporting should project the ledger; it should not be where planned controls first become searched/skipped/not-executed evidence.
- Progressive collection should rebuild the offer graph after each fast batch, targeted control, aggregate probe, or provider poll, then stop only when completeness/source/time/decision-stability limits are reached.
- Absence language belongs in structured evidence: distinguish “all direct offers returned by live provider under request X” from “all possible flights”.
- Add RED tests before promotion: trigger/no-trigger cases, mocked provider evidence projection, executable coverage/aggregate controls, `offer_graph.frontier` visibility, material-delta prioritization, renderer baggage wording, source-boundary caveats, and schema validation.

## Human/User Answer Renderer Maintenance

Use this when improving final user-visible flight output. The current seam is `data.agent_report.user_answer` → `flight_search_user_answer.v3` → `user_answer.rendered_text` → final Telegram/Markdown answer. `diagnostics.human_answer` is a debug mirror and must not be used as fallback final prose.

- Implement user-answer contract changes in `cli/flights_cli/reporting/final_answer_contract.py` and compatibility/human rendering changes in `human_answer_renderer.py` / `output.py`.
- Preserve provider neutrality: renderer input is normalized report fields, not provider client objects, booking URLs, cache semantics, or provider caveat text.
- Test negative format guarantees: no `agent report:`, `Best CLI-ranked option`, `Coverage diagnostics`, `provider_aggregate_candidate`, `provider-aggregate:`, pipe tables, or raw `probe_id` in user-facing text.
- For connected itineraries, tests must assert per-segment flight times, reject collapsed whole-journey ranges, and cover overnight/multi-day layovers where a later segment date must be visible inline.

Focused renderer/contract suite after renderer changes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest   tests/test_human_answer_renderer.py   tests/test_agent_report_contract.py   tests/test_final_answer_contract.py   tests/test_catalog_answer_contract.py   tests/test_flight_display.py   tests/test_provider_aggregate_candidates.py -q
```

Then run the full flight-search suite before reporting completion when behavior changed.

## Version Bump Checklist

When bumping the skill/CLI version, keep aligned:

- source `SKILL.md` frontmatter;
- source `cli/pyproject.toml`;
- source `cli/flights_cli/__init__.py`;
- tests that assert CLI version, doctor envelope, or human doctor output.

Do not change schema version constants unless the schema contract changes incompatibly.

## Generated Artifact Cleanup

Before final reporting, check for generated files under the skill tree without creating bytecode:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_ROOT="$HERMES_HOME/skills/productivity/flight-search"
PYTHONDONTWRITEBYTECODE=1 SKILL_ROOT="$SKILL_ROOT" python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ['SKILL_ROOT'])
hits = []
for path in root.rglob('*'):
    if path.name in {'__pycache__', '.pytest_cache'} or path.suffix == '.pyc' or path.name.endswith('.egg-info'):
        hits.append(str(path))
print('
'.join(hits))
PY
```

Generated artifacts must be intentionally cleaned or reported. Prefer `PYTHONDONTWRITEBYTECODE=1` for validation commands.

## Markdown Reference Governance

Canonical active references are bounded to six logical directions, plus bounded adjacent rail comparison:

1. `references/report-contract.md` — how to read `agent_report`, contract lifecycle, and renderer contract.
2. `references/source-boundaries.md` — evidence classes, absence, airports, connections, ticketing, OTA/smart-route semantics.
3. `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
4. `references/debug-playbook.md` — targeted probes and route-family exception patterns.
5. `references/direct-date-window.md` — direct/nonstop inventory over a bounded date range; per-date direct-only probes and compact availability output.
6. `references/cli-maintenance.md` — source/runtime, schema/tests, provider ports, CLI-surface simplification, generated artifacts, dead-code/duplicate cleanup, and this reference lifecycle.
7. `references/rail-rzd-live-pricing.md` — bounded train-price comparison after a flight search.

Do not add a new active reference for every incident, smoke run, audit, handoff, route example, migration note, or implementation report. First extract durable rules into the appropriate canonical reference or test; leave raw history to session search. Add another active reference only when a new stable direction cannot be expressed in the canonical files.

Before final reporting after Markdown consolidation:

- Confirm the canonical Markdown set explicitly.
- Confirm no new incident, runbook, audit, handoff, smoke, or implementation-report Markdown was added.
- Link from `SKILL.md` only to canonical references.
- Keep provider/airport policy in `references/provider-aware-airport-priority.md`; cross-reference it instead of duplicating provider-specific rules across docs.
- Verify noncanonical runtime-only Markdown files are gone and source/runtime Markdown parity holds after sync.
