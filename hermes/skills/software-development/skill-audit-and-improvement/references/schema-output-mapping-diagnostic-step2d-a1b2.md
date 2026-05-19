# Step 2D-A1b-2D Report-Shape and Mapping Diagnostic

Use this case note when a schema-output mapping acceptance sweep reports surprising `cli.exists` values or a high-confidence mapping whose scope/evidence looks wrong.

## Scope boundary

Keep the diagnostic read-only unless the user explicitly asks for a fix:

- inspect saved JSON reports first;
- validate saved audit reports with `validate_audit_report.py` only;
- read source/docs/tests for evidence;
- do not run audited skill CLI commands;
- do not use `--deep-cli`, `--strict`, or `--enforce-cli`;
- do not validate audited CLI outputs against per-skill schemas.

## Diagnostic sequence

1. Open the actual report JSON, not only the acceptance summary.
2. Check `$.cli.exists`, `$.cli` inventory keys, `$.cli_contract_schemas`, `$.top_level_schemas`, and `$.checks.cli_contract.{status,mode,enforced,execution_performed}`.
3. If the summary says `cli.exists=null/false` but `$.cli.exists` and inventory are correct, classify it as an extraction/report-reading artifact, not a report regression.
4. Extract the full `$.checks.schema_contract.schema_output_mappings[]` and record schema path, output name, command hint, mapping kind, confidence, scope, evidence paths, and snippets.
5. For each high-confidence mapping, verify that evidence belongs to the same contract surface. A builder that consumes `agent_report` is not evidence that `agent_report.v1.schema.json` maps to that builder.
6. Compare docs/source/tests evidence before deciding whether the issue is summary ranking, detector calibration, missed docs evidence, or a false positive.

## Flight-search calibration example

For `productivity/flight-search`, the direct CLI report mapping is:

- schema: `cli/flights_cli/contracts/agent_report.v1.schema.json`;
- output: `data.agent_report`;
- command hint: `python3 -m flights_cli --json route live-assemble ... --agent-brief` or equivalent `flights --json route live-assemble ... --agent-brief`;
- expected kind/scope when docs evidence is present: `docs_explicit` / `cli_output`.

Evidence pattern:

- `SKILL.md` golden path says to run `route live-assemble --agent-brief` and read `data.agent_report`;
- `cli/README.md` says `--agent-brief` emits only `data.agent_report` and validates it against packaged `agent_report.v1` JSON Schema;
- `services/agent_report.py` builds, validates, and attaches `data["agent_report"]`;
- `services/agent_report_contract.py` owns `AGENT_REPORT_SCHEMA_RESOURCE = "agent_report.v1.schema.json"` and `validate_agent_report(...)`;
- `tests/test_agent_report_contract.py` loads the schema resource and validates a synthetic report.

The final-answer/user-answer mapping is separate:

- schema: `cli/flights_cli/contracts/flight_search_user_answer.v1.schema.json`;
- surface: `reporting/final_answer_contract.py`;
- builder/validator: `build_user_answer_contract(...)`, `validate_user_answer_contract(...)`;
- scope: `final_answer_contract`;
- `command_hint` may be `null`.

## Classification guide

- `EXTRACTION_ARTIFACT`: acceptance/summary code looked at the wrong path, but the report still contains correct inventory.
- `REPORT_CLI_FIELD_REGRESSION`: the actual report no longer emits `$.cli.exists`/inventory for CLI skills.
- `MAPPING_OK_BUT_SUMMARY_MISLEADING`: correct mapping exists, but top-mapping display selected a less useful row.
- `MAPPING_RANKING_CALIBRATION_NEEDED`: correct docs/CLI mapping exists but is ranked behind another valid mapping.
- `MAPPING_FALSE_POSITIVE`: schema is linked to the wrong builder/validator/scope.
- `MAPPING_MISSED_DOCS_EXPLICIT`: docs evidence exists but no `docs_explicit` mapping is emitted.

## Blocker rule

Treat these as blockers before docs/template update:

- no high-confidence mapping for an expected required schema;
- `agent_report.v1.schema.json` mapped to `flight_search_user_answer` builder/validator;
- docs-explicit CLI output evidence exists but detector emits no `docs_explicit` mapping;
- CLI skills no longer emit any CLI inventory field;
- report validation fails;
- audited skill CLI command was executed in a static-only diagnostic.