# Static CLI/Schema Inventory Step 1 Case

Use this reference when extending `audit_skill.py`, `validate_audit_report.py`, or `schemas/audit-report.schema.json` for CLI/schema contract enforcement.

## Session lesson

Step 1 of CLI/schema enforcement should inventory contract surfaces without proving or enforcing them. The audit report must clearly separate:

- **static existence/inventory** — `cli/` exists, entrypoints inferred, schema-like files found, JSON claims/mutation/wrapper hints detected;
- **runtime proof** — doctor/help/tests/schema validation executed and passed.

For Step 1, runtime proof is intentionally absent:

- `checks.cli_contract.mode = "static"`
- `checks.cli_contract.enforced = false`
- `checks.cli_contract.execution_performed = false`
- `checks.schema_contract.mode = "static"`
- `checks.schema_contract.enforced = false`
- `checks.schema_contract.validation_performed = false`
- skipped reason states doctor/help/tests/schema runtime validation were not executed.

## Implementation shape that worked

- Add small pure helpers for static inventory: pyproject parsing, entrypoint inference, schema-file inventory, line-based claim/candidate scans.
- Keep all audited skill CLI discovery read-only: file reads, JSON/TOML parsing, regex scans only.
- Do not add subprocess execution for audited skill commands, `doctor`, `help`, tests, package install, or schema runtime validation in this phase.
- Report CLI-owned schemas separately from top-level schemas so nested `cli/**/contracts/*.json` surfaces are not lost.
- Emit non-blocking findings for static surfaces: JSON claims, mutation candidates, wrapper candidates, schema surfaces, unresolved entrypoints.

## Compatibility guardrail

When extending the audit JSON contract, add compatibility fixtures for old reports. In this case an independent review caught that `finding.evidence` had become required by `schemas/audit-report.schema.json` / `validate_audit_report.py`, while older valid reports could omit it. The fix was to keep `evidence` optional and add a test validating an old report with a finding but no `evidence` key.

Rule: new report sections may be optional or additive; do not make old fields newly required unless `schema_version` changes and consumers are migrated.

## Validation pattern

- Unit tests for pure inventory functions / report shape.
- AST syntax checks for changed Python scripts with `PYTHONDONTWRITEBYTECODE=1`.
- Validate a newly emitted `audit_skill.py --json` report with `validate_audit_report.py`.
- Validate at least one old-shaped report fixture.
- Run an independent blocker-only review for schema/report-contract changes.

## Runtime-only source caveat

If the active Hermes path resolves to a release directory that is not a git repo, edit the actual runtime skill only when that is the requested/local scope. For provenance, create a temporary git repo containing the runtime skill copy before running repo-dependent audit commands. Report that no commit/push was performed.

## Step 1.5 acceptance/read-back pattern

After implementing static CLI/schema inventory, run an acceptance sweep against real runtime skills, not only unit fixtures:

1. Discover runtime skills with `cli/` by filesystem search under `/home/konstantin/.hermes/skills`; do not assume the known list is complete.
2. Select at least two no-`cli/` skills as negative controls.
3. Because `audit_skill.py` requires a git repo with `skills/`, copy the selected runtime skills into a temporary repo (for example `/tmp/skill_audit_step1_5_acceptance/repo`), `git init`, commit the fixture tree, then run audits with `--repo <tmp-repo> --path skills/<category>/<skill> --json --output <report>`.
4. Validate every emitted report with `scripts/validate_audit_report.py`.
5. For each real `cli/` skill, assert the static-only contract fields: `cli.exists=true`, `checks.cli_contract.mode=static`, `enforced=false`, `execution_performed=false`, explicit skipped executable-check reason, `checks.schema_contract.mode=static`, `enforced=false`, `validation_performed=false`, and the inventory arrays are present.
6. For no-`cli/` controls, assert `checks.cli_contract.status=not_applicable`, `execution_performed=false`, and no CLI hard-failure finding.
7. Check real-world surfaces: `cli_contract_schemas` detects obvious `cli/**/contracts/*.json` and `cli/**/*.schema.json`; JSON claims without schemas warn rather than error; mutation and wrapper candidates are recorded but do not hard-fail.
8. Re-run unit tests, AST syntax checks, new-report schema validation, and compatibility fixtures for old/minimal reports, list-shaped `checks`, and old findings without `evidence`.

Keep this as static verification only. Do not run audited skill CLI commands, `doctor`, `help`, tests, package installs, or schema runtime validation during Step 1.5. High heuristic counts for JSON/mutation/wrapper candidates are warnings/observations, not blockers, unless they break report validity or imply execution proof.