# Step 2D-A0 Schema-Output Mapping Survey

Use this case note before implementing or calibrating static schema-output mapping detection in `audit_skill.py`.

## Scope boundary

Step 2D-A0 / Step 2D-A1 must stay static-only:

- do not run audited skill CLI commands;
- do not use `--deep-cli`;
- do not validate CLI outputs against per-skill schemas;
- do not add `--enforce-cli`, `--strict`, or enforcement semantics.

The useful output is advisory inventory such as `schema_output_mappings[]`, not proof that runtime output conforms.

## Mapping confidence rules

High-confidence mappings require an explicit schema path/name plus an output, command, builder, validator, or test reference in docs/source/tests.

Support these mapping kinds:

- `docs_explicit` — docs say a command or mode emits an output object and name the schema/schema version nearby.
- `tests_explicit` — tests load a schema resource or schema file and validate/assert fields for a named output object.
- `code_explicit` — code has schema constants/resources plus named builders/validators such as `build_*_contract`, `validate_*_contract`, or `load_*_schema`.
- `report_contract` — central report/envelope schemas owned by the auditor or another report generator.
- `naming_inference` — schema filename and output/builder names share a strong basename but no direct reference exists; keep this low-confidence/advisory.
- `absent` — no schema exists or no plausible mapping evidence exists.

Generic mentions of `JSON`, `schema`, `contract`, `doctor`, `report`, or `output` are not enough for a required/high-confidence mapping.

## Evidence boundaries and regression checks

Static mapping evidence must come from owned skill sources, not generated caches or vendored third-party content. The detector should ignore at least these directory families when walking text files:

- generated/cache: `__pycache__/`, `.pytest_cache/`, build/dist/cache output, and `*.pyc` artifacts;
- dependency/vendor trees: `node_modules/`, virtualenv directories, and plain `vendor/`.

Regression pattern for ignored evidence: create a minimal skill fixture with a real schema file plus only vendored text such as `agent_report.v1.schema.json validates data.agent_report`; assert that `detect_schema_output_mappings(...)` returns no mapping from that evidence, no evidence path starts with `vendor/`, and no high-confidence mapping is created. This catches false positives where third-party examples under `skill_dir/vendor/` are mistaken for owned output contracts.

When running acceptance for schema-output mapping changes, keep it static-only: use copied skill trees or focused unit tests, validate the auditor report JSON shape, and explicitly confirm that no audited skill CLI commands, `--deep-cli`, per-skill output-schema validation, `--strict`, or `--enforce-cli` were used.

## Real sample patterns

### flight-search: direct CLI report mapping

`productivity/flight-search` has a high-confidence direct CLI output mapping:

- schema: `cli/flights_cli/contracts/agent_report.v1.schema.json`
- output: `data.agent_report` / `agent_report.v1`
- command hint: `python3 -m flights_cli --json route live-assemble ... --agent-brief`
- evidence pattern:
  - `SKILL.md` tells agents to run `route live-assemble --agent-brief` and read `data.agent_report`;
  - `cli/README.md` says `--agent-brief` emits only `data.agent_report` and validates it against packaged `agent_report.v1` JSON Schema;
  - source builds, validates, and attaches `data["agent_report"]`;
  - tests load the schema resource, check `$id`/schema version, and validate synthetic reports.

This is the cleanest pattern for `docs_explicit` plus code/tests support.

### flight-search: final-answer/reporting contract mapping

`flight_search_user_answer.v1.schema.json` is also high confidence as a schema-to-output-object mapping, but it is not proven as a direct CLI-command emission surface:

- schema: `cli/flights_cli/contracts/flight_search_user_answer.v1.schema.json`
- output: `flight_search_user_answer.v1` / user answer contract
- command hint: `null`
- evidence pattern:
  - constants like `USER_ANSWER_SCHEMA_RESOURCE`, `USER_ANSWER_SCHEMA_VERSION`;
  - `build_user_answer_contract(...)` returns an object with that `schema_version`;
  - `validate_user_answer_contract(...)` validates it;
  - tests load the schema resource and assert contract fields.

A detector should allow `command_hint=null` and mark the surface as final-answer/reporting contract rather than direct CLI stdout.

### skill-audit-and-improvement: report-level schemas

The auditor skill owns report-level schemas rather than per-skill CLI schemas:

- `schemas/audit-report.schema.json` maps to `audit_skill.py --json` reports via `build_report(...)` and `validate_audit_report.py`.
- `schemas/cli-doctor-envelope.v1.schema.json` maps to advisory doctor envelope evidence via `validate_cli_doctor_envelope(...)` and `envelope_validation` metadata.

These should be `report_contract` mappings. Do not confuse them with audited skill CLI-owned schema enforcement.

### hh-ru: schema needed, mapping absent

`productivity/hh-ru` has a stable JSON envelope (`ok`, `command`, `data`) documented, emitted, and parsed by tests, but no schema files exist. Classify mapping as `absent` until a schema is added. This can justify a missing-schema advisory, but it cannot produce a schema-output mapping.

### no-CLI/no-schema negative controls

A skill with no CLI and no schemas, such as `creative/ascii-art`, should remain `not_applicable` with no missing-schema warning and no mapping candidates.

## Implementation advice for Step 2D-A1

Implement static `schema_output_mappings[]` detection only. Suggested fields:

```json
{
  "schema_path": "...",
  "output_name": "...",
  "command_hint": "... or null",
  "mapping_kind": "docs_explicit|tests_explicit|code_explicit|report_contract|naming_inference|absent",
  "confidence": "high|medium|low",
  "evidence": [{"path": "...", "line": 123, "snippet": "..."}],
  "notes": "..."
}
```

Keep runtime validation, command execution, strict mode, and enforcement for later explicit roadmap steps.