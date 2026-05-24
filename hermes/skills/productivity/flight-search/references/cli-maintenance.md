# CLI Maintenance Notes

Keep CLI maintenance focused on current live provider assembly and the `agent_report` contract. Use this when modifying or auditing the flight-search CLI, provider layers, route-family logic, coverage controls, or documentation.

## Workflow

- Work offline by default unless a task explicitly requires live provider access.
- Add or update a focused failing test before behavior changes.
- Test both the parser layer and subprocess CLI contract for date, profile, and flag behavior. A test that instantiates `argparse.Namespace` does not prove the CLI accepts the flag.
- Preserve `--json --agent-brief` as JSON-clean stdout.
- Keep search behavior limited to current live provider assembly and documented targeted probes.
- Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.
- If validation is interrupted, do not report completion. Report the last completed gate and the missing gate.

## JSON stdout/stderr Rules

- In `--json` mode, stdout must contain only the JSON envelope.
- Diagnostics, warnings, and provider logs belong on stderr or inside structured JSON fields.
- Do not print secrets, full credential paths, or unredacted provider URLs with sensitive query data.
- If an error occurs, return the standard JSON error envelope with a concrete layer and actionable detail.

## Provider URL Safety for FLI MCP

- Treat FLI MCP as a sidecar selected by URL/config.
- Validate URL shape before network use.
- Do not log sensitive query parameters unnecessarily.
- If the sidecar is unavailable, report degradation through provider failure fields rather than hiding the failure.

## Provider-aware Airport Priority Rules

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
- Two-stop options are reportable only when fallback is explicitly active or the report marks them as reportable.
- Three-plus connection itineraries are suppressed from normal recommendations.
- `candidate_pool_limit` is a safety/debug cap inside the active generation mode, not an answer-quality workaround. Do not raise it to hide generation-order defects.
- Use the shared stop-policy decision helper for assembly, ranking defense, provider aggregate projection, and report diagnostics. Do not reimplement reportability as a local `connections <= 2` check.
- `agent_report.v1` projects declared generation state. Do not infer fallback mode from compact projected options alone.

## Schema, Docs, and Tests Coupling

When changing `data.agent_report`:

1. Update the schema contract.
2. Update report-building code.
3. Update docs that tell agents how to read the fields.
4. Update fixtures and tests that assert the contract.
5. Re-run the focused contract tests before any broader validation.

Runtime-path pitfall: schema helpers and contract tests must support both layouts:

- source layout: `hermes/skills/...`
- runtime layout: `skills/...`

Discover schema paths by walking upward from the project/test root and current working directory, and include checked candidates in assertion errors.

Do not add answer-facing fields without documenting how the agent should use them. Do not change schema version constants unless the schema contract itself changes incompatibly.

## Version Bump Checklist

When bumping the skill/CLI version, keep these aligned:

- `hermes/skills/productivity/flight-search/SKILL.md` frontmatter.
- `hermes/skills/productivity/flight-search/cli/pyproject.toml`.
- `hermes/skills/productivity/flight-search/cli/flights_cli/__init__.py`.
- Tests that assert the CLI version, doctor envelope, or human doctor output.

Do not change schema version constants unless the schema contract itself changes incompatibly.

## Generated Artifact Cleanup

Before final reporting, check for generated files under the skill tree:

```bash
find hermes/skills/productivity/flight-search \( -name '__pycache__' -o -name '*.pyc' -o -name '.pytest_cache' -o -name '*.egg-info' \) -print
```

Generated artifacts must be intentionally cleaned or reported. Prefer `PYTHONDONTWRITEBYTECODE=1` for validation commands.

## Source, Runtime, and Mirror Validation

Source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state under `/home/konstantin/.hermes/skills/productivity/flight-search` is a separate deployment/sync surface. The legacy distribution mirror `cli/skill-clis/flights` must not be recreated; active CLI validation belongs to the owning skill's `cli/` directory.

Use this source-to-runtime gate after source docs or CLI changes and before touching runtime:

1. Verify post-merge source provenance on `main`: pull with `--ff-only`, capture branch/status/HEAD, and verify expected merge ancestry when specific commits are in scope. If source provenance or focused tests fail, stop before runtime mutation.
2. Verify version markers in `SKILL.md`, `cli/pyproject.toml`, and `cli/flights_cli/__init__.py` before and after sync.
3. Run focused source tests before sync. Include schema/contract tests when `agent_report` behavior changes, and provider/airport policy tests when dispatch rules change.
4. Back up the runtime skill to a timestamped directory under `/home/konstantin/hermes_skill_backups/` before every sync.
5. Sync with `rsync -a --delete` and generated-artifact excludes: `__pycache__/`, `pycache/`, `.pytest_cache/`, `*.pyc`, and `*.egg-info`.
6. Validate source/runtime parity with `diff -qr` using the same generated-artifact excludes.
7. Run runtime checks after sync: runtime `flights --version`, runtime `flights --json doctor`, and targeted offline tests from the runtime `cli/` directory.
8. Do not restart the Hermes gateway unless explicitly authorized. Use a new Hermes session/reset only when cached skill text must refresh.

Before claiming a source edit is ready, report branch, HEAD, dirty state, changed files, validation commands, generated-artifact status, whether the legacy mirror remains absent, and whether runtime sync was intentionally not performed. Do not describe a source edit as backed up until it is committed, pushed, and the remote branch SHA has been compared with the local HEAD.

## Supporting-File Distillation Policy

Do not delete supporting files merely because they contain obsolete provider details, dated route examples, or migration history. First extract durable workflow rules, route-family logic, airport/connection constraints, evidence boundaries, debug procedures, maintenance invariants, and agent skills. Move the distilled rules into the right active document or test, then delete the historical file only after the useful knowledge is preserved elsewhere.
