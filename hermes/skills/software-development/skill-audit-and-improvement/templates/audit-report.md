# Skill Audit Report Template

## Telegram Summary

- **Changed:** `<files/skills or no change>`
- **Why:** `<concrete cause/lesson>`
- **Golden path:** `<default route encoded, or not applicable with reason>`
- **Contract basis:** `<positive checks, negative anti-path checks, bypass surfaces, read-back proof, or not applicable with reason>`
- **Verified:** `<commands/read-back and pass/fail>`
- **Remaining:** `<baseline issues, uncertainty, or follow-ups>`
- **Rollback:** `<git revert sha | restore path from backup | previous file path>`

## Summary

- **Skill(s):** `<name>`
- **Request class:** `post-session learning | existing skill audit | new skill authoring | skill-owned CLI audit | source/runtime cleanup | distribution/custom inventory`
- **Branch/HEAD:** `<branch>` @ `<short-sha>` or `runtime-only: <path>`
- **Outcome:** `no change | patched | new reference | new template | new script | new CLI | new skill`

## Evidence Checked

- `git status --short --branch --untracked-files=all`: `<result or not applicable>`
- Target diff before edit: `<clean | dirty, summarized | runtime-only read-back>`
- Peer skills read: `<list>`
- Related skills loaded: `<list>`
- Runtime/source assumptions verified: `<yes/no + notes>`
- Static audit result: `<audit_skill.py summary or runtime fallback>`

## Static Findings

1. **Trigger clarity:** `<finding>`
2. **Executability:** `<finding>`
3. **Source/runtime correctness:** `<finding>`
4. **Safety/side effects:** `<finding>`
5. **Verification discipline:** `<finding>`
6. **Library architecture:** `<finding>`
7. **Behavior delta:** `<finding or not applicable>`
8. **Golden path and contract enforcement:** `<finding or not applicable>`

## Deep Audit Findings (optional)

Use this section when the request is semantic/deep quality, user-corrected behavior, or a high-risk skill.

- **Behavior before:** `<what the previous skill likely allowed the agent to miss or do poorly>`
- **Behavior after:** `<what the updated skill makes the agent do differently>`
- **Golden path:** `<first/default route a competent future agent should take>`
- **Anti-paths / bypass surfaces:** `<wrong routes plus scripts, CLIs, bridges, wrappers, cron helpers, env-var overrides, direct API helpers, and documented examples checked>`
- **Contract basis:** `<positive smoke/read-back, negative fail-closed checks, bypass coverage, mutation/read-back proof>`
- **Mistake prevented:** `<specific recurring error, unsafe shortcut, or user correction>`
- **Evidence source:** `<scenario, session lesson, static audit, docs, support file, tool output>`
- **Scenario replay result:** `<simple/edge/failure/dangerous scenario + pass/fail/needs follow-up>`
- **Remaining uncertainty:** `<what is not proven yet>`
- **Next check:** `<next scenario, static gate, pilot, source commit, CI, or fresh-session verification>`

## Changes Made

- `<path>` — `<why>`
- `<path>` — `<why>`

## CLI Contract Audit

Status: `<pass | skipped | not_applicable | warn>`
Mode: `static`
Execution performed: `false`
Entrypoints:
- `<kind name/module path confidence source | none>`
Contract schemas:
- `<path scope dialect/version hints | none>`
JSON output claims:
- `<path:line claim_type snippet | none>`
Mutation candidates:
- `<path:line snippet | none>`
Wrapper/bypass candidates:
- `<path:line snippet | none>`
Executable checks skipped reason: `Step 1 implements static inventory only; doctor/help/tests/schema runtime validation not executed.`

A passing static audit does not prove CLI contract correctness. CLI doctor/help/tests/schema validation were not executed in this mode.

## CLI Executable Advisory Audit

Mode: `<static | advisory>`
Execution performed: `<true | false>`
Enforced: `false`
Help checks: `<status; commands_attempted; commands_passed; evidence ids>`
Doctor checks: `<status; commands_attempted; json_parsed; evidence ids; parse warning if any>`
Tests: `<skipped unless --run-cli-tests was provided; status/reason/evidence ids>`
Evidence entries:
- `<ev_cli_help_001 | ev_cli_doctor_001 | ev_cli_tests_001>` — `<status argv cwd exit_code duration_ms hashes/truncation>`
Skipped/blocked commands:
- `<reason | none>`
Timeouts:
- `<command ids | none>`
Warnings:
- `Executable CLI checks in --deep-cli mode are advisory in this phase. A passing advisory run does not yet imply enforced CLI contract compliance.`
- `<CLI_HELP_CHECK_FAILED | CLI_DOCTOR_CHECK_FAILED | CLI_DOCTOR_JSON_PARSE_FAILED | CLI_TESTS_FAILED | CLI_EXECUTION_TIMEOUT | CLI_EXECUTION_BLOCKED_UNSAFE | none>`

## CLI Doctor JSON Envelope Advisory Validation

Doctor attempted: `<true | false>`
JSON parsed: `<true | false>`
Envelope validation performed: `<true | false>`
Envelope status: `<pass | warn | skipped>`
Schema name: `cli-doctor-envelope.v1`
Missing required fields: `<ok, command, data, issues | none>`
Field type errors: `<field expected/actual list | none>`
ok value: `<true | false | null>`
command value: `<doctor | other | null>`
data type: `<object | array | string | number | boolean | null>`
issues count: `<number | null>`
error code: `<string | null>`
JSON root type: `<object | array | string | number | boolean | null>`
JSON top-level keys/fingerprint: `<keys and fingerprint | none>`
Advisory findings:
- `<CLI_DOCTOR_ENVELOPE_VALID | CLI_DOCTOR_ENVELOPE_INVALID | CLI_DOCTOR_ENVELOPE_MISSING_REQUIRED_FIELD | CLI_DOCTOR_ENVELOPE_FIELD_TYPE_INVALID | CLI_DOCTOR_REPORTED_NOT_OK | CLI_DOCTOR_DATA_NOT_OBJECT | CLI_DOCTOR_JSON_ROOT_NOT_OBJECT | none>`

Doctor JSON envelope validation is advisory in this phase. Invalid or incomplete envelopes produce warnings but do not enforce CLI contract compliance yet.

## JSON Schema Advisory Audit

Schema audit is advisory in this phase. Missing, invalid, or unreferenced schemas produce warnings but do not enforce CLI contract compliance yet.

- **Status:** `<pass | skipped | not_applicable | warn>`
- **Mode:** `advisory_static`
- **Enforced:** `false`
- **Validation performed:** `<true | false>`
- **Decision:** `<required | recommended | optional | not_applicable> — <summary>`
- **Decision reason codes:** `<reason_codes | none>`
- **Schema files found:** `<total>`
- **Valid JSON:** `<count>`
- **Invalid JSON:** `<count>`
- **Meta-validation:** `<meta_valid pass; meta_invalid warn; meta_validation_skipped skipped + reason if unavailable>`
- **Missing $schema:** `<count>`
- **Missing $id:** `<count>`
- **Referenced by docs:** `<count>`
- **Referenced by tests:** `<count>`
- **Missing schema advisory:** `<none | SCHEMA_REQUIRED_BUT_MISSING_ADVISORY | SCHEMA_RECOMMENDED_BUT_MISSING_ADVISORY>`
- **Advisory findings:** `<SCHEMA_FILE_DETECTED | SCHEMA_FILE_INVALID_JSON | SCHEMA_META_VALIDATION_PASSED | SCHEMA_META_VALIDATION_FAILED | SCHEMA_META_VALIDATION_SKIPPED | SCHEMA_DIALECT_MISSING | SCHEMA_DIALECT_UNKNOWN | SCHEMA_ID_MISSING | SCHEMA_NOT_REFERENCED_BY_DOCS | SCHEMA_NOT_REFERENCED_BY_TESTS | SCHEMA_TOO_OPEN_FOR_MACHINE_CONTRACT | decision finding | none>`

Schema details:
- `<path>` — `scope=<cli_contract|top_level>; json_valid=<true|false>; dialect=<draft2020-12|draft2019-09|draft-07|unknown|null>; id=<present|missing>; type=<object|array|string|number|boolean|null|mixed|unknown>; additionalProperties=<closed|open|mixed|unspecified|unknown>; version=<v1|v2|null>; docs=<true|false>; tests=<true|false>`

## Verification

Commands/read-back run:

```bash
<command or read-back check>
```

Results:

- `<check>`: `<pass/fail>`
- `<check>`: `<pass/fail>`
- `golden-path/contract fields present when required`: `<pass/fail/not applicable + reason>`
- `positive path smoke/read-back`: `<pass/fail/not applicable>`
- `negative anti-path/bypass checks`: `<pass/fail/not applicable>`
- `mutation/read-back contract`: `<pass/fail/not applicable>`
- `secret/stale/unsafe-scan check`: `<pass/fail; findings redacted>`
- `generated artifacts check`: `<pass/fail>`
- `protected context unchanged`: `<pass/fail>`

## Remaining / Baseline Issues

- `<issue>` — `<why not fixed in this scope>`

## Commit / Rollback

Commit:

```bash
<sha + message | no commit: runtime-only/doc-only/out of scope>
```

Rollback:

```bash
<git revert <sha> | restore previous runtime file backup | manual path list>
```
