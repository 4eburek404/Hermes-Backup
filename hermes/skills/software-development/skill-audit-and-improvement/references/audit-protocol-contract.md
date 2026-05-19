# Stable Audit Protocol Contract

Use this reference when skill-library work raises questions about JSON reports, skill-owned CLIs, CI gates, or where to store audit rules.

## Core Decision

Do **not** spread stable JSON reports or CLI contracts across every skill by default. Use one stable audit protocol owned by `skill-audit-and-improvement` and implemented through `scripts/audit_skill.py`.

Every skill should be machine-auditable, but every skill does not need its own JSON artifact or CLI.

## Layering

- `skill-audit-and-improvement/SKILL.md` owns the procedure and routing rule.
- `references/audit-protocol-contract.md` owns the design rationale and contract notes.
- `schemas/` should own JSON Schema files once implemented.
- `scripts/audit_skill.py` should emit the stable machine-readable audit report.
- `scripts/validate_audit_report.py` must validate emitted `--json` reports against `schemas/audit-report.schema.json` whenever the report contract, schema, or report generator changes.
- `fact_store` may keep a compact retrieval pointer to the canonical skill/reference.
- `USER.md` is not the right layer: this is project architecture, not a personal communication preference.
- `MEMORY.md` is not the right layer unless the rule becomes a true always-on self-protection pointer; prefer skill routing first.

## JSON Contract Policy

JSON is mandatory for:

- `audit_skill.py --json`;
- `audit_skill.py --changed --json`;
- secret/redaction scanners;
- stale-path scanners;
- repository-wide skills inventory;
- CI reports;
- `doctor --json` for owning CLIs that have a real machine consumer.

JSON is optional/useful for deterministic scripts that return findings or evidence.

JSON is not needed by default for:

- ordinary instructional `SKILL.md` files;
- `references/*.md`;
- `templates/*.md`;
- short one-off helper scripts with no downstream machine consumer.

## CLI Policy

A skill-owned CLI is justified only when the workflow has repeated executable logic, live checks, redaction requirements, multiple subcommands, CI integration, stateful/multi-file validation, or a mature tool contract.

For most skills, prefer:

```text
SKILL.md
references/
templates/
scripts/
```

Add a CLI only when scripts become too large or when humans/agents/CI need a stable command interface.

## Static Baseline Inventory Contract

Step 1 of CLI/schema enforcement is static inventory only. `audit_skill.py` may detect that a skill-owned `cli/` exists, infer entrypoints, list Python/test/schema/JSON files, and record static JSON-output, mutation, and wrapper/bypass hints. It must not execute the audited skill's CLI commands, `doctor`, `help`, tests, package installs, or runtime schema validation in this mode.

Reports must distinguish static inventory from proof: `checks.cli_contract.execution_performed=false`, `checks.schema_contract.validation_performed=false`, `enforced=false`, and the skipped executable-check reason must state that doctor/help/tests/schema runtime validation were not executed.

## Step 2A Advisory Executable CLI Audit Contract

Step 2A adds `audit_skill.py --deep-cli` as an explicit opt-in mode for a small advisory executable audit. It is not default behavior and must remain non-blocking in this phase.

Flags:

- `--deep-cli` enables advisory CLI execution.
- `--no-exec` overrides `--deep-cli`; no subprocesses run and the report must set `checks.cli_contract.execution_performed=false` with a `--no-exec` reason.
- `--cli-timeout-sec N` applies per command.
- `--max-output-bytes N` bounds stdout/stderr previews while hashes cover full captured output.
- `--run-cli-tests` is required before Step 2A runs `cli/tests`; tests are not run automatically under `--deep-cli`.

Mandatory execution guardrails:

- Run subprocesses with `shell=False`, argv lists only, `capture_output=True`, `text=True`, `check=False`, explicit timeout, and `cwd` set to the audited skill's `cli/` directory where applicable.
- Use a sanitized minimal environment: set `PYTHONDONTWRITEBYTECODE=1`, isolate `HOME` to a temporary directory when practical, preserve only minimal variables such as `PATH` and locale/PYTHONPATH if needed, and never print environment values.
- Block mutating or side-effect candidates by default, including `--apply`, `--yes`, `--force`, `--delete`, `--write`, `--install`, `--deploy`, `--send`, `--commit`, `--push`, `rm`, `mv`, non-temporary `cp`, `systemctl`, and `git push`.
- Do not run live/network/provider commands unless a future phase explicitly classifies them safe.

Step 2A check scope:

- Help checks may run up to three high-confidence static-inventory entrypoints (`python3 -m <module> --help` or `python3 <file> --help`).
- Doctor checks may run at most one likely JSON doctor surface (`--json doctor` or `doctor --json`) when static docs indicate both doctor and JSON.
- CLI tests run only with `--run-cli-tests`, via `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` in `cli/`.

Schema validation enforcement is not part of Step 2A. Report-schema validation of `audit_skill.py` output remains required when changing the report generator/schema, but audited CLI-owned schemas and doctor JSON are not enforced yet. `checks.schema_contract.validation_performed=false`, `checks.*.enforced=false`, and CLI failures/timeouts/invalid JSON produce advisory warnings rather than blocking errors unless `audit_skill.py` itself crashes or the emitted audit report is invalid.

## Step 2B Advisory Doctor JSON Envelope Contract

Step 2B validates doctor JSON envelope shape only when `--deep-cli` executes a doctor command and stdout parses as JSON. The validation is advisory: invalid or incomplete envelopes produce warning findings, but do not enforce CLI contract compliance and do not become blockers by themselves.

Baseline envelope artifact: `schemas/cli-doctor-envelope.v1.schema.json`.

Minimum expected envelope:

```json
{
  "ok": true,
  "command": "doctor",
  "data": {},
  "issues": []
}
```

Required fields: `ok`, `command`, `data`, `issues`. `ok` must be boolean, `command` string, `issues` array. `data` may be any JSON type in Step 2B, though object is preferred and non-object data is recorded as an info-level advisory note. Optional `error` must be object or null; `error.code` and `error.message`, when present, must be strings.

`ok=false` is not a schema violation; it is a doctor result signal. With a valid envelope shape it remains non-blocking, but the report records `CLI_DOCTOR_REPORTED_NOT_OK` and usually sets the doctor-check summary to `warn`.

The JSON root must be an object for the baseline envelope. Array/string/number/boolean/null roots are advisory invalid envelope shapes, not execution crashes.

Step 2B does not validate per-skill CLI-owned schemas, does not enforce JSON Schema contracts, and does not replace future per-command JSON Schema validation. It also must not make doctor command discovery more aggressive than Step 2A.

## Step 2C Advisory Schema-File Audit and Decision Gate

Step 2C audits discovered schema files and classifies whether a schema contract is needed. It remains advisory-only:

- Parse discovered schema candidates as JSON and inspect schema metadata (`$schema`, `$id`/`id`, title, type, properties, required, `$defs`/`definitions`, and `additionalProperties`).
- Optionally run JSON Schema meta-validation if the `jsonschema` library is already importable; if unavailable, record `SCHEMA_META_VALIDATION_SKIPPED` and keep the audit non-blocking.
- Detect whether schema files are referenced from docs/source and tests.
- Emit `checks.schema_contract.mode="advisory_static"`, `enforced=false`, and a decision level: `required`, `recommended`, `optional`, or `not_applicable`.

Step 2C does **not** validate CLI command output against per-skill schemas, does **not** enforce schema compliance, does **not** require every skill to have JSON Schema, and does **not** introduce `--enforce-cli` or `--strict`.

JSON Schema is required or recommended only when there is a machine-readable contract surface: stable JSON output, doctor JSON surface, downstream agent/CI/baseline/golden consumers, wrapper/report parsing of JSON fields, redaction-sensitive structured output, or explicit schema-output contracts. Mostly prose/manual skills and skills without CLI/JSON/schema surfaces are `optional` or `not_applicable`; not all skills need JSON Schema.

Missing schema in a required or recommended context is an advisory warning only (`SCHEMA_REQUIRED_BUT_MISSING_ADVISORY` or `SCHEMA_RECOMMENDED_BUT_MISSING_ADVISORY`) until a future enforcement phase. Per-skill output validation and enforcement are future steps.

## Step 2D-A1b Schema Output Mapping Contract

Step 2D-A1b adds `schema_output_mappings[]` as advisory, statically produced evidence for likely relationships between schema files and structured outputs. It does not validate command output against schemas, does not enforce contract compliance, and does not change `schema_contract.status` by itself when mappings are absent.

Supported mapping kinds: `docs_explicit`, `code_explicit`, `tests_explicit`, `report_contract`, and `naming_inference`.

Supported scopes: `cli_output`, `report_contract`, `final_answer_contract`, and `unknown`.

Confidence semantics:

- `high`: explicit evidence from docs, code, tests, or report-contract fields.
- `medium`: strong structural match but less direct evidence.
- `low`: naming-only inference.

Known examples:

- `flight-search` `agent_report.v1.schema.json` maps to `data.agent_report` via `docs_explicit` / `cli_output` / `--agent-brief`.
- `flight-search` `flight_search_user_answer.v1.schema.json` maps to `final_answer_contract` via `code_explicit`.

## Golden Path Contract Policy

Every skill that steers a fragile workflow must have a golden-path contract:

- **Golden path:** the default route a future agent should take first.
- **Anti-paths:** plausible wrong routes that are blocked, demoted to explicit fallback, or marked unsupported.
- **Bypass surface inventory:** every script, CLI, bridge, wrapper, cron helper, env-var override, direct API helper, and documented example that could reach the same behavior.
- **Positive checks:** smoke/read-back evidence that the golden path works or is plausibly available.
- **Negative checks:** fail-closed tests proving the anti-path cannot silently execute through any bypass surface.
- **Mutation proof:** duplicate/search/read-back or equivalent state verification after writes.

This is a contract, not a preference. A skill may say “prefer X” only when choosing Y is harmless. If Y is the known-wrong route or would trigger external side effects, the skill must make Y fail closed or require explicit fallback approval.

Do not add a per-skill CLI just to satisfy this policy. A small `scripts/validate_contract.py` or audit-script check is enough when it names the invariants and returns machine-readable pass/fail.

## Degradation Gate Shape

The target enforcement loop is:

```text
schema → audit_skill.py → baseline/no-regression compare → CI required check → branch protection → blocker-only review
```

The goal is that degradation becomes hard because the repository rejects bad changes, not because an agent remembers a preference.

## Session Lessons (consolidated from 2026-05-07 and 2026-05-08 audit sessions)

### Provenance Before Editing

Branch, HEAD, status, and target diffs must be checked before modifying skill files. This prevents stale assumptions about runtime paths, old CLI layouts, and dirty development state. Always verify live repo state — do not rely on memory of what files look like.

### Dirty Worktree Provenance

After a verified scoped commit, remaining dirty files are not automatically failed cleanup or safe to commit. Classify each dirty path as:
1. committed-work leftovers that should be finished or separately committed;
2. active-plan work that should stay dirty or move to its own branch;
3. completed-but-unarchived plan notes;
4. unrelated or pre-existing changes that must not be staged.

Run `audit_skill.py --changed --json` before recommending commit; do not print secret-like values from findings.

### Audit Script Hardening Lessons

- `audit_skill.py` must remain read-only: no Git staging/committing/checkout/reset operations, no destructive shell commands, no permission-changing commands, no mutation of audited skills.
- Reject report outputs inside the repo (`OUTPUT_INSIDE_REPO`).
- Avoid repo-local caches/artifacts during tests (`PYTHONDONTWRITEBYTECODE=1`, `pytest -p no:cacheprovider`).
- Redact entire rest-of-line after sensitive keys, not just the first token. Also redact generic `Bearer ...` segments even when the YAML key is not in the sensitive-key allowlist.
- For deleted nested `SKILL.md` files, derive the affected skill dir from `path.parent`, not from fixed-depth assumptions.

### Master Plan Synthesis Pattern

When a skill-audit task has multiple overlapping plans:
1. Treat existing plans as inputs, not automatically current truth. Reconcile into one master execution map.
2. Preserve companion plans unless the user explicitly approves lifecycle changes.
3. For each phase, include practical profit/benefit, not only tasks.
4. Save durable multi-step synthesized plans under `/home/konstantin/docs/plans/` with machine-readable status.
5. Verify after saving: file exists, `Current status: ...` is present, code fences balanced, no secret-like values, `knowledge --json plans audit` can detect the plan.

## Protected Context Pitfall

Before trying to store this kind of rule in `USER.md`, `MEMORY.md`, or `SOUL.md`, show the proposed diff and analyze whether the rule belongs there. If the write is rejected or would exceed capacity, report that no protected context file changed and route the rule to the correct canonical layer instead.
