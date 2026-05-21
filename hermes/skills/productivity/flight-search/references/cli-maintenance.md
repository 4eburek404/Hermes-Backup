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

Source edits happen under `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`. Runtime state under `/home/konstantin/.hermes/skills/productivity/flight-search` is a separate deployment/sync surface. The legacy distribution mirror `cli/skill-clis/flights` is retired and must not be recreated; active CLI validation belongs to the owning skill's `cli/` directory.

When the user asks whether the flight-search skill or CLI “got backup”, verify both Git backup and runtime/source equality before answering:

1. In `/home/konstantin/src/Hermes-Backup`, capture `git status --short --branch --untracked-files=all`, `git rev-parse HEAD`, `git log -1 --oneline --decorate`, `git remote -v`, and `git ls-remote origin refs/heads/main`. A clean local branch plus matching remote HEAD proves the committed backup is present; it does not prove ignored generated caches are clean.
2. Compare the active runtime skill with the backed-up current source path using `diff -qr` with generated-artifact excludes (`__pycache__`, `*.pyc`, `.pytest_cache`, `*.egg-info`). Then verify `SKILL.md`, `cli/pyproject.toml`, and `cli/flights_cli/__init__.py` versions, bytes, and SHA-256 on both sides before saying they match.
3. Validate the current CLI from both roots with `PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --version` and, when useful, `--json doctor`. Prefer direct version output over inferring from file text only.
4. Verify that `/home/konstantin/src/Hermes-Backup/cli/skill-clis/flights` is absent. If it exists, report it as a stale legacy standalone mirror, not the active skill-owned CLI; current backup scripts should not recreate it.
5. Check generated artifacts separately with `find` or a small path walk. Ignored `.pytest_cache`/`__pycache__` under the backup/source tree are not pushed backup content; report them as cleanup-only unless the user asked to delete them.

Before claiming a source edit is ready, report branch, HEAD, dirty state, changed files, validation commands, generated-artifact status, whether the legacy mirror remains absent, and whether runtime sync was intentionally not performed.

## Supporting-File Distillation Policy

Do not delete supporting files merely because they contain obsolete provider details, dated route examples, or migration history. First extract durable workflow rules, route-family logic, airport/connection constraints, evidence boundaries, debug procedures, maintenance invariants, and agent skills. Move the distilled rules into the right active document or test, then delete the historical file only after the useful knowledge is preserved elsewhere.
