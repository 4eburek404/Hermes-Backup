# Step 2C.5A Schema-Decision Noise Check Case Note

Use this case note when checking whether the Step 2C schema-decision gate is over-classifying ordinary skills as `required`.

## Scope pattern

- Keep the run read-only against real skill state.
- Do not run `--deep-cli`.
- Do not execute skill-owned CLIs.
- Do not add enforcement flags such as `--enforce-cli` or `--strict`.
- Do not validate skill CLI outputs against per-skill schemas in this phase.
- If `audit_skill.py` needs a repo layout but the target skills live only in runtime state, copy the selected skill directories into a temporary repo under `/tmp`, `git init` + commit the snapshot, and audit that copy only.

## Minimal evidence matrix

For each selected skill, save a JSON report and validate it with `scripts/validate_audit_report.py`. Extract at least:

- skill path/name;
- `cli.exists`;
- `len(cli.json_output_claims)`;
- top-level schema count;
- CLI contract schema count;
- `checks.schema_contract.status`;
- `checks.schema_contract.decision.level`;
- `checks.schema_contract.decision.reason_codes`;
- Step 2C/schema-contract finding codes only;
- unrelated blocker count;
- report validation result.

## Calibration rule

Generic mentions of `JSON`, `schema`, `contract`, `doctor`, `report`, or `output` alone should not justify `required`.

Treat `required` as justified only when stronger evidence appears, such as:

- CI, baseline, golden, or contract-test claims;
- agent-report or machine-consumer claims;
- structured output consumed by another tool;
- tests or wrappers parsing JSON fields;
- explicit stable JSON envelope / schema-output contract;
- CLI-owned schema files plus JSON/machine contract evidence;
- redaction-sensitive structured output where a schema contract would protect safety boundaries.

## Interpretation examples from 2026-05-15

- `skill-audit-and-improvement`: `required` was correct because the skill owns stable audit report schemas, validator/baseline/golden-contract language, tests/schema references, wrapper JSON parsing, and redaction-sensitive output. `status=warn` was also correct because valid schemas still had advisory quality/linkage warnings such as missing test reference or open/mixed `additionalProperties` policy.
- `flight-search`: `required` was correct because it has a CLI, many JSON output claims, CLI-owned contract schemas, `agent_report` contract evidence, doctor JSON surface, tests/schema references, and machine/agent-report language.
- `hh-ru`: `required` was correct when evidence included an agent-workflow stable JSON envelope, tests using `json.loads` and asserting JSON fields, implementation emitting `ok/command/data` envelopes, and redaction-sensitive response-header output. Missing schemas should surface as advisory warnings, not enforcement.
- no-CLI/no-schema negative controls should be `not_applicable` and should not emit missing-schema warnings.

## Report conclusion rule

- If a suspect skill is `TRUE_REQUIRED` or `UNCLEAR` but explainable, proceed to the next implementation/calibration phase.
- If it is only `SHOULD_BE_RECOMMENDED`, recommend a separate small calibration patch before the next phase.
