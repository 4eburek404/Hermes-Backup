# CLI Maintenance Notes

Use this when modifying or auditing the flight-search CLI, provider layers, route-family logic, coverage controls, report contract, skill Markdown, or source/runtime sync. Keep maintenance behind the `SKILL.md` maintenance gate; ordinary route search should stay traveler-facing.

## Workflow

- Before any flight-search maintenance/refactor implementation, compare source and runtime first: paths, `SKILL.md` version, CLI version markers, source/runtime parity, and runtime-only reference docs. If runtime is newer or differs semantically, stop before code changes and preserve/merge the latest runtime guidance into source rather than starting from a stale checkout.
- Work offline by default unless the task explicitly requires live provider access.
- For behavior changes, add or update a focused failing test before implementation.
- Test both parser/subprocess CLI contract and internal helpers. A test that instantiates `argparse.Namespace` does not prove the CLI accepts the flag.
- Preserve `--json --agent-brief` as JSON-clean stdout.
- Keep search behavior limited to current live provider assembly and documented targeted probes.
- Static catalogs are metadata only; flight options come from live provider assembly.
- If validation is interrupted, do not report completion. Report the last completed gate and the missing gate.

## JSON stdout/stderr Rules

- In `--json` mode, stdout must contain only the JSON envelope.
- Diagnostics, warnings, and provider logs belong on stderr or inside structured JSON fields.
- Do not print secrets, full credential paths, or unredacted provider URLs with sensitive query data.
- If an error occurs, return the standard JSON error envelope with a concrete layer and actionable detail.

## Provider and Airport Policy Coupling

The durable source contract lives in `references/provider-aware-airport-priority.md`. Keep implementation, tests, and docs aligned with these invariants:

- Active provider paths are KupiBilet and FLI; static catalogs are metadata only.
- `IST` is exact-airport `IST` by default; `SAW` requires an explicit user request.
- London defaults to `LHR` first, with `LGW` deferred until `LHR` has no accepted/viable offers; `STN` and `LTN` are excluded by default.
- KupiBilet handles Moscow as `MOW` city-code first; exact `SVO`/`DME`/`VKO` fallback is deferred and must not run in parallel when the city-code request has accepted offers.
- FLI is exact-airport only and must not receive city-code `LON` by default.
- City-code results must be post-validated against actual airport scope, and reports must display actual airport codes rather than only request city codes.

## Route-Family and Coverage-Control Rules

- Route-family metadata and segment-spec identity belong in shared route-graph helpers, not duplicated in docs, dry planners, or live planners.
- Keep RU domestic, RU-touching international, global non-RU, Asia/Oceania, and structurally constrained route logic consistent across public builders.
- Domestic-RU routing must be decided in one shared layer and propagated through `route plan`, assembly, and `route live-assemble`.
- For domestic Russian round trips, assert the direct return segment `DEST -> ORIGIN` and absence of default international hubs unless explicitly requested.
- Moscow/SVO controls are first-class controls when relevant, not fallback-only behavior.
- New live coverage probes need query-budget design: provider-aware cache keys, in-run de-duplication, bounded per-provider concurrency, rate-limit backoff, and visible live/cache/stale labels.

## Skill-to-CLI Promotion Rules

Use this when operational logic in `SKILL.md` starts compensating for deterministic CLI behavior. Prefer moving repeatable decision mechanics into the CLI/report contract rather than relying on agent prose.

- Promote behavior, not wording: encode constraints, controls, evidence, stop reasons, and frontier roles as structured report fields; keep final prose in the renderer.
- Treat the target architecture as constraints → executable evidence plan → progressive probes/polls → first-class offer graph → decision frontier/report. A report-only `offer_graph` or post-hoc `coverage_diagnostics` is not enough for completeness-sensitive behavior.
- Move `ProbeExecutionLedger`-style state into execution/scheduling when it affects search completeness. Reporting should project the ledger; it should not be the first place that planned controls become searched/skipped/not-executed evidence.
- For simple domestic round trips with decision-leading direct options, implement a bounded `kb-roundtrip --direct-only` style live control inside `route live-assemble` before asking the agent to run it manually. Preserve baggage, hand-luggage, seats-left, price deltas, and source caveats in `agent_report`.
- Material round-trip bundle differences must be compared against normalized options before rendering, not by parsing `human_answer.text`. Treat price, baggage/hand-luggage, seats, ticketing/source confidence, and return-time alternatives as decision-changing dimensions.
- Progressive collection should rebuild the offer graph after each fast batch, targeted control, aggregate probe, or provider poll, then stop only when a completeness limit is reached, the provider/source is exhausted, the decision frontier no longer changes, or an explicit time/query budget expires. Model Skyscanner-style live search as initial/create result plus poll/dobor; never treat the first provider response as complete by default.
- Coverage and aggregate-control flags must not live as side paths. `coverage-mode`, `coverage-control`, carrier/full-route aggregate controls, direct controls, and round-trip package checks should all compile to a common `ProbeIntent`/evidence-goal model with provider capability and terminal status.
- Absence language belongs in structured evidence: distinguish “all direct offers returned by live provider under request X” from “all possible flights”. Never let the renderer overclaim beyond source boundaries.
- Add RED tests before promotion: trigger/no-trigger cases, mocked provider evidence projection, executable coverage/aggregate controls, `offer_graph.frontier` visibility, material-delta prioritization, renderer baggage wording, source-boundary caveats, and schema validation with `Draft202012Validator`.

## CLI/Orchestrator Audit Checklist

Use this when asked to audit or refactor the flight-search CLI rather than run a traveler search.

- Start with provenance: source/runtime path, git branch/HEAD/status, and whether the runtime skill is intentionally ahead of source.
- Dump the parser/subparser tree from `flights_cli.cli.build_parser()` and group flags by leaf command; do not infer documented flags from prose alone. In this CLI, `route kb-assemble` and `route live-assemble` share the live assembly runner, while `route assemble` is offline assembly over provided segment results.
- Trace each decision flag end-to-end: CLI parser → args/default mutations such as `agent_mode`/`agent_brief` → route plan/live plan → probe dispatch/provider selection → assembly/ranking → report projection. Mark flags as core path, output preset, side path, diagnostic-only, or partially integrated.
- Pay special attention to `coverage-mode`, `coverage-control`, `aggregate-control-*`, `provider-policy`, `direct-only`, round-trip/package modes, `agent-report`, `agent-mode`, `agent-brief`, and `human_answer`; these commonly blur algorithmic behavior with reporting defaults.
- Distinguish projections from causes. If `offer_graph`, `coverage_diagnostics`, `missing_evidence`, `frontier`, or `human_answer` are created only inside reporting/builders after probes finish, they are not yet controlling search completeness.
- Validate audit conclusions with focused offline contracts where possible. Some unittest modules import `helpers` as a top-level test helper; run with `PYTHONPATH=tests:.` from the CLI root when needed, e.g. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m unittest tests.test_coverage_controls tests.test_probe_ledger tests.test_agent_report_p0_completeness`.

## CLI Surface and Contract Simplification

Use this when the user asks whether flags, schemas, or commands are redundant, overloaded, or agent/user paths are too complex. For larger redesign work, also load `references/cli-redesign-governance.md`; it records the target decomposition into report level, output profile, evidence preset, canonical user answer, provider ports, unified probe ledger, and stop-policy contract.

- Separate three concerns before recommending removals: **search/evidence semantics** (provider calls, probes, coverage controls), **decision semantics** (assembly, ranking, stop policy, frontier), and **output semantics** (JSON size, `agent_report`, `human_answer`, brief rendering). Do not describe a flag as output-only until tracing whether it changes provider calls or evidence budgets.
- In the current CLI, `--agent-mode` is overloaded: it enables `agent_report`, changes output caps, and can set `aggregate_control_limit=10`. Treat it as a compatibility preset, not a clean output flag. Prefer a future split into an explicit report/output selector plus an explicit evidence/coverage preset.
- `--agent-report` is the thin wrapper concept: attach and validate `data.agent_report` without otherwise changing output or search budgets.
- `--agent-brief` should be treated as a compact-output selector only after refactor; if it implies `agent_mode`, call out the inherited evidence/budget side effect in audits and tests.
- Keep ordinary user commands narrow. Hide or classify as advanced/debug the knobs for candidate pool limits, included raw/ranked/rejected bodies, segment-result inclusion, live-cache TTL, direct-route-intel TTL, fail-fast, day-offset fanout, coverage-control internals, and aggregate-control internals.
- Prefer one public route-search wrapper over parallel user-facing variants. Provider-specific commands (`kb-search`, `kb-roundtrip`, `fli-search`, `fli-dates`) and offline `route plan/validate/rank/assemble` are diagnostics/development surfaces unless the user explicitly asks for provider-level proof.
- If `route kb-assemble` remains, document or implement it as a compatibility alias for `route live-assemble --provider-policy kupibilet`; avoid maintaining duplicate user guidance for both.
- Audit provider abstractions for real use, not just existence. `ProviderCapabilities`, `ProviderProbeResult`, and provider registry are valuable only if segment and aggregate probes dispatch through common provider adapters; otherwise they are scaffolding that can drift while live code still branches on provider names.
- Aggregate/full-route/carrier controls should compile to the same probe-intent/ledger path as segment probes. Avoid separate mini-dispatchers that duplicate cache flags, provider calls, failure classification, and summary projection.
- When `services/agent_report.py` is only an attach/validate seam, keep imports minimal. Do not let unused re-export imports hide the real builder/renderer/projector ownership.
- For schema simplification, keep `flight_search_user_answer.v1` as the compact user-facing contract and avoid expanding `agent_report.v1` as a catch-all. If `agent_report` needs to carry evidence, frontier, and user answer at once, consider decomposing into evidence/probe status, offer frontier, and user answer subcontracts.
- Treat `human_answer`, `display`, and `answer_lines` as potentially overlapping presentation layers. Pick one canonical user-answer contract and render from it; avoid parallel final-prose sources inside the agent report.

## Assembly and Stop-Policy Rules

- Candidate generation is stop-policy-first. Generate direct/one-stop preferred candidates before fallback candidates.
- Do not let two-stop or three-plus routes consume `candidate_pool_limit` while preferred candidates still exist.
- Two-stop options are reportable only when fallback is explicitly active or the report marks them reportable.
- Three-plus connection itineraries are suppressed from normal recommendations.
- `candidate_pool_limit` is a safety/debug cap inside the active generation mode, not an answer-quality workaround.
- Use the shared stop-policy decision helper for assembly, ranking defense, provider aggregate projection, and report diagnostics. Do not reimplement reportability as a local `connections <= 2` check.
- `agent_report.v1` projects declared generation state. Do not infer fallback mode from compact projected options alone.

## Schema, Docs, and Tests Coupling

When changing `data.agent_report`:

1. Update the schema contract.
2. Update report-building code.
3. Update docs that tell agents how to read the fields.
4. Update fixtures and tests that assert the contract.
5. If the change introduces a primary decision layer such as `offer_graph`, add an architecture/doc contract test that forces `SKILL.md` and `references/report-contract.md` to name the new read order; do not rely on code/schema tests alone.
6. Re-run the focused contract tests before broader validation.

Runtime-path pitfall: schema helpers and contract tests must support both layouts:

- source checkout layout: a nested `hermes` directory followed by `/skills/...`;
- runtime layout: `$HERMES_HOME/skills/...` (or `$HOME/.hermes` + `/skills/...`).

Discover schema paths by walking upward from the project/test root and current working directory, and include checked candidates in assertion errors.

Do not add answer-facing fields without documenting how the agent should use them. Do not change schema version constants unless the schema contract itself changes incompatibly.

## Human Answer Renderer Maintenance

Use this when improving final user-visible flight output. The provider-neutral seam is `data.agent_report` -> `human_answer` -> Telegram/Markdown answer; do not copy provider-specific plugin formatter wording one-to-one.

- Implement final-output changes in `cli/flights_cli/reporting/human_answer_renderer.py`.
- Keep `human_answer` in `cli/flights_cli/contracts/agent_report.v1.schema.json` and `cli/tests/test_agent_report_contract.py` synchronized with renderer changes.
- Preserve provider neutrality: renderer input is normalized report fields, not provider client objects, booking URLs, cache semantics, or provider caveat text.
- Test negative format guarantees: no `agent report:`, `Best CLI-ranked option`, `Coverage diagnostics`, `provider_aggregate_candidate`, `provider-aggregate:`, pipe tables, or raw `probe_id` in user-facing text.
- For connected itineraries, tests must assert per-segment flight times such as `SU1437 18:10-18:55 -> SU1844 20:35-21:55`, reject collapsed whole-journey ranges, and cover overnight/multi-day layovers where a later segment date must be visible inline.

Focused renderer/contract suite after renderer changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_human_answer_renderer.py \
  tests/test_agent_report_contract.py \
  tests/test_final_answer_contract.py \
  tests/test_flight_display.py \
  tests/test_provider_aggregate_candidates.py -q
```

Then run the full flight-search suite before reporting completion.

## Version Bump Checklist

When bumping the skill/CLI version, keep these aligned:

- source `SKILL.md` frontmatter in the flight-search skill root;
- source `cli/pyproject.toml`;
- source `cli/flights_cli/__init__.py`;
- tests that assert the CLI version, doctor envelope, or human doctor output.

Do not change schema version constants unless the schema contract itself changes incompatibly.

## Source, Runtime, and Mirror Validation

Current source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state lives under `$HERMES_HOME/skills/productivity/flight-search` (usually `$HOME/.hermes/skills/productivity/flight-search`) and is a separate deployment/sync surface. The active release path may intentionally exclude this runtime/user skill. The legacy distribution mirror `cli/skill-clis/flights` must not be recreated.

Before saying which version is current, run the compact local maintenance report when the CLI is available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maintenance check
```

Then check separately when deeper evidence is required:

- runtime skill `SKILL.md` version, bytes, and SHA-256;
- runtime CLI markers: `cli/pyproject.toml`, `cli/flights_cli/__init__.py`, and `python3 -m flights_cli --version` from the runtime `cli/` directory;
- active Hermes release: whether `~/.hermes/hermes-agent/skills/productivity/flight-search` exists;
- local source checkout: `/home/konstantin/src/Hermes-Backup/hermes`, branch, HEAD, dirty state, and ahead/behind status;
- GitHub publication state only when asked for published link/current remote version.

If runtime is newer than GitHub, say so explicitly: operationally loaded runtime may be ahead of published source until source changes are committed and pushed.

## Runtime-to-Source Gate Before Publishing

Use this when the user asks to “sync with runtime” before committing or pushing a flight-search change. Treat runtime as an explicit input surface, not as a cache to overwrite blindly.

1. Verify source repo branch, `HEAD`, dirty status, origin URL, and whether the feature branch already has an upstream.
2. Compare runtime and source with generated-artifact excludes. Under `set -euo pipefail`, wrap `diff -qr ... | wc -l` as `(diff -qr ... || true) | wc -l` or run `diff ... || true`; otherwise a real diff can abort the provenance command before later checks run.
3. Inspect changed runtime files before copying. If runtime has task-relevant docs/contract changes, sync runtime -> source with `rsync -a --delete` plus excludes for `__pycache__/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
4. Validate source/runtime parity after sync, run focused contract/doc tests and the full offline suite when the change touches `agent_report`, report contract, or user-facing decision logic.
5. Clean generated artifacts created by tests before staging.
6. Stage only the runtime-sync files that changed, run `git diff --cached --check` and an allowlist guard, commit the sync if needed, then push and verify local/remote SHA equality.

## Source-to-Runtime Gate

Use this gate after source docs or CLI changes and before touching runtime:

1. Verify source provenance: branch, HEAD, status, and expected target diff.
2. Verify version markers in `SKILL.md`, `cli/pyproject.toml`, and `cli/flights_cli/__init__.py` when version is in scope.
3. Run focused source tests before sync. Include schema/contract tests when `agent_report` behavior changes, and provider/airport policy tests when dispatch rules change.
4. Back up the runtime skill before every sync. If no shape is specified, use a clearly named timestamped sibling or backup-area copy and verify size/hash.
5. Compare source and runtime before overwriting. If runtime has semantic, non-generated changes that are absent from the source/main being deployed, show the concise diff and ask whether to overwrite runtime, preserve it via a follow-up source branch/PR, or leave runtime intentionally ahead. Do not silently erase useful runtime-only operating rules. Treat runtime-only reference docs and a newer runtime `SKILL.md` version as semantic drift, not generated artifacts; stop before `rsync --delete` unless the user explicitly chooses overwrite.
6. Before real sync, run a dry-run `rsync -a --delete --itemize-changes` with generated-artifact excludes; validate deletion paths are intended.
7. Sync with generated-artifact excludes: `__pycache__/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
8. Validate source/runtime parity with `diff -qr` using the same excludes, then run key-file checksums for marker/config files when requested.
9. Run runtime checks after sync from the runtime `cli/` directory: `python -m flights_cli --json doctor`, help/contract smoke for newly touched commands, and targeted offline tests when available.
10. Clean only generated runtime artifacts created by validation and rerun parity.
11. Do not restart the Hermes gateway unless explicitly authorized. Use a new Hermes session/reset only when cached skill text must refresh.

## Generated Artifact Cleanup

Before final reporting, check for generated files under the skill tree without creating bytecode:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_ROOT="$HERMES_HOME/skills/productivity/flight-search"
PYTHONDONTWRITEBYTECODE=1 SKILL_ROOT="$SKILL_ROOT" python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ['SKILL_ROOT'])
patterns = ('__pycache__', '.pytest_cache')
hits = []
for path in root.rglob('*'):
    if path.name in patterns or path.suffix == '.pyc' or path.name.endswith('.egg-info'):
        hits.append(str(path))
print('\n'.join(hits))
PY
```

Generated artifacts must be intentionally cleaned or reported. Prefer `PYTHONDONTWRITEBYTECODE=1` for validation commands.

## Markdown Reference Governance

Canonical active references are bounded to five logical directions:

1. `references/report-contract.md` — how to read `agent_report` and render the final answer.
2. `references/source-boundaries.md` — evidence classes, absence, airports, connections, ticketing, OTA/smart-route semantics.
3. `references/provider-aware-airport-priority.md` — provider/airport dispatch and city-code policy.
4. `references/debug-playbook.md` — targeted probes and route-family exception patterns.
5. `references/cli-maintenance.md` — source/runtime, schema/tests, sync, generated artifacts, and this reference lifecycle.

Do not add a new active reference for every incident, smoke run, audit, handoff, route example, or implementation report. First extract durable workflow rules, route-family logic, evidence boundaries, debug procedures, maintenance invariants, and agent skills. Put the distilled rule into the appropriate canonical reference or test; leave raw history to session search. Add a sixth active reference only when a new stable direction cannot be expressed in the five canonical files.

Before final reporting after Markdown consolidation:

- Confirm the canonical Markdown set explicitly.
- Confirm no new incident, runbook, audit, handoff, smoke, or implementation-report Markdown was added.
- Link from `SKILL.md` only to canonical references.
- Keep provider/airport policy in `references/provider-aware-airport-priority.md`; cross-reference it instead of duplicating provider-specific rules across docs.
- If tests enforce documentation invariants, update the guard when the durable rule changes rather than preserving stale historical exceptions.
- Verify noncanonical runtime-only Markdown files are gone and source/runtime Markdown parity holds after sync.
