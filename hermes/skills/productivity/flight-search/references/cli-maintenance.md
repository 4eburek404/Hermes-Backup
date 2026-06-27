# CLI Maintenance Notes

Use this when modifying or auditing the flight-search CLI, provider layers, route-family logic, coverage controls, report contract, skill Markdown, or source/runtime sync. Keep maintenance behind the `SKILL.md` maintenance gate; ordinary route search should stay traveler-facing.

Important UX boundary: the flight-search CLI is an agent-facing implementation tool, not a user-operated product. The end user should not be expected to run commands or interpret CLI help/output; the user receives only the final rendered search result. Optimize the CLI surface for deterministic agent execution, stable machine-readable contracts, diagnostics, and maintenance—not for exposing every knob as a human-facing option.

## Workflow

- Start with provenance: runtime path, source path, branch, HEAD, dirty state, version markers, and whether runtime is intentionally ahead of source.
- Before any maintenance/refactor implementation, compare source and runtime with generated-artifact excludes. If runtime is newer or semantically different, preserve/merge runtime guidance into source before `rsync --delete`.
- Work offline by default unless live provider access is the subject of the task.
- For behavior changes, add/update a focused failing test before implementation.
- Test parser/subprocess CLI contract and internal helpers. A test that instantiates `argparse.Namespace` does not prove the CLI accepts the flag.
- Preserve `--json --agent-brief` as JSON-clean stdout.
- Keep search behavior limited to current live provider assembly and documented targeted probes.
- Static catalogs are metadata only; flight options come from live provider assembly.
- Historical audit/session/proposal notes should not remain active references. Distill durable rules into this file, the other canonical references, executable report fields, or tests; leave raw history to session search.
- Do not publish copy-paste command blocks for unimplemented/future surfaces. If a future command is worth keeping, label it as backlog prose and keep the implemented replacement path nearby.
- If validation is interrupted, report the last completed gate and the missing gate; do not report completion.

## JSON stdout/stderr Rules

- In `--json` mode, stdout must contain only the JSON envelope.
- Diagnostics, warnings, and provider logs belong on stderr or inside structured JSON fields.
- Do not print secrets, full credential paths, or unredacted provider URLs with sensitive query data.
- If an error occurs, return the standard JSON error envelope with a concrete layer and actionable detail.

## Source, Runtime, and Mirror Validation

Current source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state lives under `$HERMES_HOME/skills/productivity/flight-search` (usually `$HOME/.hermes/skills/productivity/flight-search`) and is a separate deployment/sync surface. The active Hermes release path may intentionally exclude this runtime/user skill. Do not recreate the retired distribution mirror formerly known as `skill-clis/flights`.

Before saying which version is current, run the compact local maintenance report when the CLI is available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maint check
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
9. Run runtime checks after sync from runtime `cli/`: `python3 -m flights_cli --json maint doctor`, help/contract smoke for touched commands, and targeted offline tests when available.
10. Clean only generated runtime artifacts created by validation and rerun parity.
11. Do not restart the Hermes gateway unless explicitly authorized. Use a new Hermes session/reset only when cached skill text must refresh.

## Contract Registry and Lifecycle

The current report/user-answer registry lives in `references/report-contract.md`; do not duplicate or fork it here. Maintenance changes that touch reports must still update the schema, report-building code, docs that tell agents how to read fields, fixtures/tests, and focused contract tests in one change.

Before adding or documenting another final-answer/report surface, classify every touched surface as current, retired/projection, shadow, or proposed according to `references/report-contract.md`. Do not introduce another v1/v2/v3 layer until the ownership map is clear.

Public JSON tests should assert nested `agent_report.v2` paths such as `report["frontier"]["recommended_options"]`, not top-level legacy aliases.

## CLI Surface and Contract Simplification

Use this when the user asks whether flags, schemas, commands, or agent/user paths are redundant, overloaded, or becoming a “свалка”. Do not answer CLI-surface questions from the Golden Path or a sampled subset alone: first enumerate every parser leaf command with `--help`, inspect `cli.py`/`command_surface.py`, and search tests/docs for the disputed flags or aliases. Report which layer was sampled vs fully inventoried.

Parser registration in `cli.py` owns the runtime command tree. `command_surface.py` is policy/contract metadata for manifest, maintenance, diagnostics, live-provider, and catalog-refresh classification; it must not grow into a second parser registry. Tests that need command coverage should inspect the built `argparse` tree and compare policy metadata against real leaf commands instead of keeping parallel active-command argv maps.

When the user is confused by `v1/v2/v3`, `user_answer`, `user_output`, `final_answer`, `human_answer`, `display`, or `answer_lines`, first audit whether this is a real multi-version implementation or only misleading names. Current durable finding: the active public line is single-path (`agent_report.v2` → `flight_search_user_answer.v3` → `user_answer.rendered_text`); `user_output` and `flight_search_final_answer` are not active code contracts. The confusing surfaces are diagnostics only: `flight_human_answer.v1` is a mirror-only diagnostic projection, `flight_display.v1` is itinerary diagnostics, and diagnostic `answer_lines` are summary lines. Before adding new schemas, add/update a contract registry with logical names (`search_request`, `search_result`, `agent_report`, `user_answer`) and statuses (`current`, `diagnostic_mirror_only`, `diagnostic_projection`, `retired/rejected`, `proposed`) so agents do not reason directly in raw version labels.

Prefer internal intent-name cleanup before wire-version bumps: canonical user-answer code lives in `reporting/user_answer.py`; diagnostic human-answer mirror code lives in `reporting/projections/human_answer_mirror.py` and must not render independently; diagnostic `answer_lines` are summary lines; `display` is itinerary diagnostics. Do not bump `agent_report.v2` or `flight_search_user_answer.v3` merely to rename Python modules. Bump wire versions only when emitted JSON changes incompatibly.

Separate three concerns before removals:

1. Search/evidence semantics — provider calls, probes, coverage controls.
2. Decision semantics — assembly, ranking, stop policy, frontier.
3. Output semantics — JSON size, `agent_report`, `human_answer`, brief rendering.

External CLI practice anchors for this decision:

- `clig.dev`: human-first defaults, composable stdout/stderr/exit codes, help/examples at every level, avoid noisy debug output in normal commands.
- Microsoft `System.CommandLine` guidance: parent commands should be grouping areas; options parameterize commands and should not become hidden actions.
- Kubernetes plugin model: custom/advanced workflows can be separate executables on `PATH`, discoverable as subcommands, without bloating the core binary.
- Twelve-Factor admin processes: maintenance/admin tasks should run as one-off processes shipped with the same code/config/dependencies as the app.
- Docker `system prune` pattern: destructive maintenance is an explicit maintenance command, shows what will be removed, and requires confirmation unless `--force`.
- Machine-readable output guidance: JSON/structured output must be stable, stdout-clean, color-free, and append-only within a version series.
- Doctor command pattern: collect enough environment/config/provenance to triage while redacting security-sensitive details.

Rules:

- When the user is already confused by current structure, prioritize **structural cleanup planning before adversarial future-breakage**. A good plan first states the current canonical path, identifies misleading names, and gives a concrete merge/split/rename order. For this CLI, the current canonical cleanup order is: contract registry → `reporting/user_answer.py` owns `flight_search_user_answer.v3` → diagnostic projections live under `reporting/projections/` → `agent_report_projector.py` owns `agent_report.v2` projection without changing the wire version → typed `SearchRequest`/`FlowDecision`/`EvidencePlan` behind `search --request`.
- For flight-search structural plans, keep one implementation binary first (`flights`) with role namespaces (`flights search`, `flights diagnose`, `flights maint`). Separate executable names such as `flights-diagnose`/`flights-maint` may be aliases later, but should not introduce separate implementation trees. Do not switch parser frameworks or delete `agent_report.v2` just to simplify the plan; retain compatibility until migration tests prove consumers moved.
- Before approving or implementing a CLI-surface refactor plan, do an adversarial architecture pass **after** the structural cleanup order is clear: try to break it through version/name drift, multiple final-text sources, stdout/stderr error ambiguity, JSON-as-flag-zoo, misclassified `flow_decision`, provider-port bypasses, diagnostic commands becoming production answers, hidden maintenance side effects, source/runtime overwrites, `$ref` packaging failures, schema meta-validation without subprocess output validation, round-trip capability gaps, stale cache caveats, secret/log leakage, executable drift, and premature legacy removal. Label each item as observed seam, existing guardrail, refactor hazard, or current bug; do not present hazards as code facts without provenance. For each break scenario, record the concrete closing rule/test before implementation.
- Before approving or implementing a CLI-surface refactor plan, audit the dependency order explicitly: source/runtime ownership gate → contract registry/naming cleanup → request/result schema foundation → flow decision/evidence plan → new production `flights search` entrypoint → provider/evidence boundary cleanup → diagnostics/maintenance executable split → legacy removal → skill docs update. Do not delete legacy commands/flags before replacement contracts and migration tests exist.
- Treat `flow_decision` as a first-class contract seam, not prose: classify `intent_class`, `market_class`, `evidence_class`, routing strategy, provider plan, and limitations before command/provider reasoning. A JSON request without this normalized decision layer only moves the old flag/command ambiguity into JSON.
- For strict agent-facing JSON, decide and test error-channel semantics up front: preferred contract is stdout contains exactly one JSON result envelope for both `ok=true` and `ok=false`; stderr is logs/warnings only and never required for parsing. If errors remain stderr-only, do not claim stdout is always a complete machine contract.
- Split static catalog freshness from live provider cache policy. Static catalogs are metadata only; catalog-dependent commands may auto-refresh missing or older-than-2-weeks metadata before planning, while live cache is evidence freshness and must be represented in the report/result.
- Context7/CPython argparse guidance: keep `add_subparsers(required=True)` at every command level, attach leaf handlers with `set_defaults(func=...)`, and use parent parsers with `add_help=False` for shared option groups instead of copy-pasting flags.
- Do not treat “agent mode” as one design primitive. It can conflate report attachment, output shape, and evidence budget.
- Do not solve overload by adding a larger public taxonomy (`none/user/agent/debug/human/json`, `--format`, `--report`, `--evidence`) without a concrete consumer and contract.
- For agent-only CLI refactors, design the production path as strict machine contract first: `flights search --request request.json --json`, with `flight_search_request.v1` validated before provider calls and a single stdout JSON result envelope validated before printing. Keep `agent_report.v2` and `flight_search_user_answer.v3` as nested active contracts; do not create another independent final-answer prose layer.
- Keep the canonical user answer path explicit: `data.agent_report.user_answer.rendered_text`. If a result envelope exposes a derived `rendered_text` mirror, tests must prove exact equality with that canonical field.
- Split agent-facing surfaces by operational role: production live search (`flights`), diagnostics/evidence/raw probes (`flights-diagnose`), and maintenance/source-runtime/catalog/cleanup (`flights-maint`). Provider-specific probes, raw candidates, rejected pairs, trace, coverage controls, and offline route internals belong in diagnostics, not ordinary search.
- `--agent-report` should be a thin wrapper that attaches/validates `data.agent_report` without changing search budget.
- `--agent-brief` should trim output only; if it implies legacy `agent_mode`, call out inherited evidence/budget side effects in audits and tests.
- `--agent-mode` is a legacy compatibility preset, not a new design surface; remove it after replacement production/diagnostic contracts exist.
- Keep ordinary user commands narrow. Hide or classify as advanced/debug the knobs for candidate pool limits, raw/ranked/rejected bodies, live-cache TTL, direct-route-intel TTL, fail-fast, day-offset fanout, coverage-control internals, and aggregate-control internals.
- Prefer one public route-search wrapper over parallel user-facing variants. Provider-specific commands, `diagnose plan --request`, and offline `route validate/rank/assemble` are diagnostics/development surfaces unless the user explicitly asks for provider-level proof.
- Do not preserve compatibility aliases just because older tests referenced them; production search and diagnostic provider override surfaces are already separate.

## Provider Port Rule

Do not remove the provider port abstraction. Complete it:

- `ports/providers.py` owns `FlightProviderPort`, `ProviderCapabilities`, `ProviderProbeResult`, provider/probe/evidence/cache literals.
- `adapters/providers/registry.py` returns concrete provider adapters, not only descriptors.
- provider adapters own cached search calls, normalization, post-validation, summaries, source boundaries, error mapping, retry/transport policy, and provider-specific request strategy.
- common search core owns request schema, route/evidence plan, progressive collection loop, dedupe, cache policy, probe ledger, offer graph, ranking, report/result schemas, and renderer.
- provider policy owns mapping from route segment + request evidence policy to eligible providers using capabilities and airport/route policy.
- `execution/probe_dispatcher.py` loops over provider adapters and translates `ProviderProbeResult` into probe ledger/outcome types.
- aggregate controls call provider adapter `search_aggregate(...)` or receive structured `not_supported`; they must not contain provider-only algorithm branches.
- production orchestration must not call provider-specific functions such as `fetch_kupibilet_search` directly. Keep provider-specific commands and human renderers in diagnostics or adapter-owned projections, not in the production answer path.
- If KupiBilet round-trip remains outside the port while `diagnose kb-roundtrip` exists, document that capability boundary explicitly; otherwise model it as a typed provider-port method with tests.

Pitfalls:

- After moving direct calls out of `execution/`, update tests to patch adapter seams; do not re-export old symbols just to keep tests green.
- Prefer positive seam/behavior tests over permanent string-absence tests. Temporary audits may search for forbidden provider symbols, but durable tests should prove production orchestration uses `FlightProviderPort`/`ProviderProbeResult`, preserves dedupe/fail-fast semantics, and surfaces provider boundaries in the report.
- Avoid a registry that stores capabilities/descriptors while separate code constructs adapters elsewhere.
- If a provider cannot support aggregate probes, return structured `not_supported` so reports explain the source boundary instead of silently skipping it.
- Preserve dedupe and fail-fast semantics in the dispatcher adapter bridge; these are execution semantics, not provider-specific behavior.

## Provider and Airport Policy Coupling

The authoritative rules live in `references/provider-aware-airport-priority.md`; do not duplicate them here. When maintaining the CLI, tests, or docs, read that file for city/airport dispatch invariants, KupiBilet MOW city-code behavior, FLI exact-airport policy, and airport interchangeability rules.

## Route-Family and Coverage-Control Rules

- Route-family metadata and segment-spec identity belong in shared route-graph helpers, not duplicated in docs, dry planners, or live planners.
- Keep RU domestic, RU-touching international, global non-RU, Asia/Oceania, and structurally constrained route logic consistent across public builders.
- Domestic-RU routing must be decided in one shared layer and propagated through `diagnose plan --request`, assembly, and `search --request`.
- For domestic Russian round trips, assert the direct return segment `DEST -> ORIGIN` and absence of default international hubs unless explicitly requested.
- Moscow/SVO controls are first-class controls when relevant, not deferred-only behavior.
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

Use this when improving final user-visible flight output. The current seam is `data.agent_report.user_answer` → `flight_search_user_answer.v3` → `user_answer.rendered_text` → final Telegram/Markdown answer. `diagnostics.human_answer` is a mirror-only diagnostic projection and must not render, fallback, or be used as an alternative final-prose source.

- Implement user-answer contract changes in `cli/flights_cli/reporting/user_answer.py`; `reporting/projections/human_answer_mirror.py` and `output.py` may only mirror or select `user_answer.rendered_text`.
- Preserve provider neutrality: renderer input is normalized report fields, not provider client objects, booking URLs, cache semantics, or provider caveat text.
- Test negative format guarantees: no `agent report:`, `Best CLI-ranked option`, `Coverage diagnostics`, `provider_aggregate_candidate`, `provider-aggregate:`, pipe tables, raw `probe_id`, raw risk badges (`single_pnr_unproven`, `baggage_unknown`), or English caveats (`single PNR`, `through fare`, `booking screen`) in user-facing text.
- For every positive catalog answer, use one deterministic compact multiline shape from `catalog.items[*].agent_display`: first line is `N. FLIGHT DD.MM Origin city - Destination city HH:MM HH:MM (arrival DD.MM when different) AIRCRAFT в пути H:MM`; continuation segment lines and the price line are indented by four spaces. Do not create a second compact pipe renderer in diagnostics.
- Do not append absence/negative-evidence wording such as “не нашёл в выполненных live/probe источниках…” to a positive answer that already lists viable options. Reserve `truth_language.negative_wording` for no-viable-options / absence-scope answers; positive catalogs should keep only actionable purchase checks and source-boundary caveats that affect booking.
- For connected itineraries, tests must assert per-segment flight times, reject collapsed whole-journey ranges, and cover overnight/multi-day layovers where a later segment date must be visible inline.

Focused renderer/contract suite after renderer changes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest   tests/test_human_answer_mirror.py   tests/test_agent_report_contract.py   tests/test_user_answer_contract.py   tests/test_catalog_answer_contract.py   tests/test_flight_display.py   tests/test_provider_aggregate_candidates.py -q
```

Then run the full flight-search suite before reporting completion when behavior changed.

## Maintenance Pitfalls

- Mixing source, runtime, and temporary checkouts without naming the evidence layer.
- Calling a refactor “complete” while source/runtime parity still has semantic diffs.
- Letting `--agent-*` compatibility flags become a larger public flag matrix instead of separating search/evidence, decision, and output concerns internally.
- Treating MCP `outputSchema`, prompt text, or debug mirrors (`diagnostics.human_answer`, `diagnostics.display`, `diagnostics.answer_lines`) as the domain contract; the enforceable layer lives in `references/report-contract.md` plus schema/builder/validator/tests.
- Reintroducing provider execution shortcuts: segment and aggregate probes should go through provider adapters/ports, not direct provider-specific branches in `execution/*`.
- Treating `--agent-brief` as permission to narrow evidence scope. It may trim output only; explicit evidence/search controls must still be honored.
- During dead-code cleanup, classify `Protocol` ellipsis methods as interface declarations, not runtime stubs; use layer-specific names for helpers with different responsibilities.

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
print('\n'.join(hits))
PY
```

Generated artifacts must be intentionally cleaned or reported. Prefer `PYTHONDONTWRITEBYTECODE=1` for validation commands.

## Markdown Reference Governance

Canonical active references are the index plus eight owner files:

0. `references/index.md` — canonical reference owner map and routing hub from `SKILL.md`.
1. `references/report-contract.md` — how to read `agent_report`, contract lifecycle, and renderer contract.
2. `references/source-boundaries.md` — evidence classes, absence, airports, connections, ticketing, OTA/smart-route semantics.
3. `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
4. `references/pipeline-reference.md` — current data flow, flow decision, evidence plan, direct-priority/all-direct mechanics, reporting projection, and data artifacts.
5. `references/debug-playbook.md` — targeted probes and bounded exception/debug patterns.
6. `references/direct-date-window.md` — direct/nonstop inventory over a bounded date range.
7. `references/rail-rzd-live-pricing.md` — bounded official-RZD train-price comparison after a flight search.
8. `references/cli-maintenance.md` — source/runtime, schema/tests, provider ports, CLI-surface simplification, generated artifacts, dead-code/duplicate cleanup, and this reference lifecycle.

Do not add a new active reference for every incident, smoke run, audit, handoff, route example, migration note, or implementation report. First extract durable rules into the appropriate canonical reference or test; leave raw history to session search. Add another active reference only when a new stable direction cannot be expressed in the canonical files.

Before final reporting after Markdown consolidation:

- Confirm the canonical Markdown set explicitly.
- Confirm no new incident, runbook, audit, handoff, smoke, or implementation-report Markdown was added.
- Link from `SKILL.md` to `references/index.md` for reference routing; direct links to specific references are allowed only for hot-path invariants.
- Keep provider/airport policy in `references/provider-aware-airport-priority.md`; cross-reference it instead of duplicating provider-specific rules across docs.
- Verify noncanonical runtime-only Markdown files are gone and source/runtime Markdown parity holds after sync when runtime sync is in scope.
