# CLI and Schema Contracts

## Purpose and status

This reference defines how the skill audit helper treats skill-owned CLIs, JSON outputs, schemas, doctor envelopes, and report contracts. These checks are **advisory** unless an explicit future enforcement flag says otherwise. Advisory findings guide improvement; they do not by themselves prove a CLI contract is enforced.

## Static CLI inventory

The default audit is read-only. It may inspect:

- `cli/` files and Python module entrypoints.
- `pyproject.toml` project scripts.
- documented `python -m ...` commands that point to local skill-owned modules.
- JSON-output claims in docs or code.
- mutating command candidates and wrappers/bypass surfaces.
- schema-like files under `schemas/`, `cli/**/contracts/`, or similar local contract paths.

The static pass does **not** execute help, doctor, tests, migrations, installs, network calls, or service commands.

## Advisory executable audit

`--deep-cli` may run bounded local checks only when explicitly requested. Invariants:

- `--no-exec` wins over `--deep-cli`.
- Execute only high-confidence local entrypoints.
- Use sanitized environment and bounded timeout/output previews.
- Hash full stdout/stderr before truncating previews.
- Redact argv and output values that look like tokens, passwords, keys, cookies, DSNs, or authorization headers.
- Block mutating verbs/flags such as deploy, delete, force, write, apply, upload, publish, or destructive `--flag=value` forms.
- `--run-cli-tests` is separate and opt-in.

Blocked execution is a useful finding, not a reason to bypass the policy.

## Doctor JSON envelope

The central advisory doctor envelope is `schemas/cli-doctor-envelope.v1.schema.json`. A valid doctor object has:

- `ok`: boolean
- `command`: string, normally `doctor`
- `data`: object
- `issues`: array

Rules:

- JSON root must be an object.
- `ok: false` is a reported result, not a schema violation.
- Missing required fields or wrong types are warnings while advisory.
- Evidence records should include parse status, root type, required-field errors, field-type errors, top-level keys, output hashes, truncation flags, and redacted previews.

## Schema decision levels

Use the weakest level supported by evidence:

| Level | Meaning | Typical evidence |
|---|---|---|
| `not_applicable` | No skill-owned CLI or structured machine output. | Pure prose/docs workflow. |
| `optional` | Structured shape might help but no consumer is named. | Human-facing examples only. |
| `recommended` | JSON output or report claim exists, but consumer is unclear. | Docs mention `--json` or stable fields. |
| `required` | A repeated machine consumer, CI check, golden baseline, wrapper, or downstream parser depends on fields. | Tests parse fields, schemas are referenced, or another tool consumes output. |

Generic words like “JSON”, “schema”, “report”, “contract”, or “output” are not enough for `required`.

## Schema file audit

For each schema-like file, record:

- valid JSON or parse warning;
- `$schema` dialect presence;
- `$id` presence;
- object/array/type summary;
- version hint such as `v1`;
- `additionalProperties` policy;
- references from docs and tests;
- meta-validation result when `jsonschema` is available.

Keep `repo.skills_root` and similar report fields additive and optional unless an incompatible version bump is explicitly required.

## Schema-output mappings

Static mappings identify likely relationships between schema files and outputs. They do not validate runtime output.

High confidence requires explicit identity evidence:

- docs naming the schema and command/output field;
- code that builds or validates an object tied to the exact schema name;
- tests that reference the exact schema and output;
- report-contract fields that name the schema.

Ranking:

1. docs CLI output mapping;
2. report contract mapping;
3. exact code mapping;
4. exact tests mapping;
5. naming inference only as low/medium confidence.

Ignore evidence from generated, cache, vendor, virtualenv, or unrelated fixture directories. Parameter names such as `agent_report` are not exact schema identity by themselves.

## Report compatibility

When adding report fields:

- Keep old reports valid when the change is additive.
- Add tests for old and new shapes.
- Validate emitted JSON with `scripts/validate_audit_report.py`.
- Do not require legacy fields only to preserve a past implementation detail.

## Safety checklist

- [ ] Default audit stayed read-only.
- [ ] Any execution was explicitly requested and advisory.
- [ ] Mutating commands were blocked or skipped.
- [ ] Secret-like values were redacted before report output.
- [ ] Old report fixtures still validate after additive schema changes.
