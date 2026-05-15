# Step 2B: Advisory Doctor JSON Envelope Validation

Use this case note when extending `skill-audit-and-improvement`'s audit report contract after Step 2A safe CLI execution.

## Scope boundary

Step 2B is advisory-only:

- validate the baseline doctor JSON envelope shape only;
- do not add `--enforce-cli` or `--strict`;
- do not make CLI failures, JSON parse failures, or envelope violations blocking by themselves;
- do not validate per-skill CLI-owned schemas yet;
- do not broaden doctor command discovery beyond Step 2A's high-confidence/safe command policy.

## Baseline envelope

Central artifact: `schemas/cli-doctor-envelope.v1.schema.json`.

Minimum expected shape:

```json
{
  "ok": true,
  "command": "doctor",
  "data": {},
  "issues": []
}
```

Required fields: `ok`, `command`, `data`, `issues`.

Validation notes:

- JSON root must be an object; array/string/number/boolean/null is a warning.
- `ok` must be boolean.
- `command` must be string.
- `issues` must be an array.
- `data` may be any JSON type in Step 2B; non-object is info/advisory, not invalid.
- `ok=false` is not a schema violation. Treat it as a doctor result signal: report advisory warning when paired with issues/error, but keep envelope shape validation separate.

## Evidence normalization requirements

Command evidence should include normalized fields where practical:

- `evidence_schema_version: command-evidence.v1`
- stable `command_id`
- `argv_redacted`
- redacted stdout/stderr preview fields
- raw-output `stdout_sha256` / `stderr_sha256` retained for provenance
- output byte counts and preview byte counts
- `json_root_type`, `json_top_level_keys`, `json_fingerprint`
- `envelope_validation` object for doctor evidence

Never print environment values. Keep preview bounded by `--max-output-bytes` and redact obvious secret-like content (`Authorization:`, bearer tokens, `token=`, `api_key=`, `password=`, `secret=`).

## Regression tests that matter

Add or preserve tests for:

- valid envelope passes;
- missing required fields warn and produce `CLI_DOCTOR_ENVELOPE_MISSING_REQUIRED_FIELD`;
- invalid field types warn and produce `CLI_DOCTOR_ENVELOPE_FIELD_TYPE_INVALID`;
- JSON root array warns and produces `CLI_DOCTOR_JSON_ROOT_NOT_OBJECT`;
- `ok=false` valid shape is non-blocking and produces `CLI_DOCTOR_REPORTED_NOT_OK`;
- invalid JSON skips envelope validation without crashing;
- valid and invalid envelope reports still validate with `validate_audit_report.py`;
- old Step 1 and Step 2A shaped reports remain valid;
- secret-like stdout/stderr preview values are redacted while hashes remain present.

## Self-audit pitfall from implementation

A redaction regression test can accidentally create a `SECRET_LIKE_VALUE` blocker if it writes literal sensitive-key assignments directly into the test source (for example, a password-like or token-like key followed by an inline value). Preserve the regression by constructing sensitive key names and values from safe fragments, then assert against the constructed variables and redacted preview fields.

## Acceptance sweep pattern

After changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import ast, json
for rel in ['scripts/audit_skill.py', 'scripts/validate_audit_report.py']:
    ast.parse(Path(rel).read_text(encoding='utf-8'), filename=rel)
for rel in ['schemas/audit-report.schema.json', 'schemas/cli-doctor-envelope.v1.schema.json']:
    json.loads(Path(rel).read_text(encoding='utf-8'))
PY
```

Then emit and validate reports for:

1. fixture valid doctor envelope;
2. fixture invalid doctor envelope;
3. fixture no-CLI skill with `--deep-cli`;
4. one real runtime CLI skill only if the safe high-confidence entrypoint/doctor command is detected;
5. one real no-CLI skill.

Use temporary git repos for runtime skill copies when the live runtime tree is not a git repo. Treat unrelated real-skill findings as non-blockers for Step 2B if emitted reports validate and CLI/envelope behavior is advisory-only.
