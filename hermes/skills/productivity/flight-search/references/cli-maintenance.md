# CLI Maintenance Notes

Use this when modifying or auditing the flight-search CLI, provider layers, route-family logic, coverage controls, report contract, skill Markdown, or source/runtime sync. Keep maintenance behind the `SKILL.md` maintenance gate; ordinary route search should stay traveler-facing.

## Workflow

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
5. Re-run the focused contract tests before broader validation.

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

Before saying which version is current, check separately:

- runtime skill `SKILL.md` version, bytes, and SHA-256;
- runtime CLI markers: `cli/pyproject.toml`, `cli/flights_cli/__init__.py`, and `python3 -m flights_cli --version` from the runtime `cli/` directory;
- active Hermes release: whether `~/.hermes/hermes-agent/skills/productivity/flight-search` exists;
- local source checkout: `/home/konstantin/src/Hermes-Backup/hermes`, branch, HEAD, dirty state, and ahead/behind status;
- GitHub publication state only when asked for published link/current remote version.

If runtime is newer than GitHub, say so explicitly: operationally loaded runtime may be ahead of published source until source changes are committed and pushed.

## Source-to-Runtime Gate

Use this gate after source docs or CLI changes and before touching runtime:

1. Verify source provenance: branch, HEAD, status, and expected target diff.
2. Verify version markers in `SKILL.md`, `cli/pyproject.toml`, and `cli/flights_cli/__init__.py` when version is in scope.
3. Run focused source tests before sync. Include schema/contract tests when `agent_report` behavior changes, and provider/airport policy tests when dispatch rules change.
4. Back up the runtime skill before every sync. If no shape is specified, use a clearly named timestamped sibling or backup-area copy and verify size/hash.
5. Before real sync, run a dry-run `rsync -a --delete --itemize-changes` with generated-artifact excludes; validate deletion paths are intended.
6. Sync with generated-artifact excludes: `__pycache__/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
7. Validate source/runtime parity with `diff -qr` using the same excludes, then run key-file checksums for marker/config files when requested.
8. Run runtime checks after sync from the runtime `cli/` directory: `python -m flights_cli --json doctor`, help/contract smoke for newly touched commands, and targeted offline tests when available.
9. Clean only generated runtime artifacts created by validation and rerun parity.
10. Do not restart the Hermes gateway unless explicitly authorized. Use a new Hermes session/reset only when cached skill text must refresh.

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
