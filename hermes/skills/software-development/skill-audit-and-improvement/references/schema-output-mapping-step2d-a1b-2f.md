# Step 2D-A1b-2F case note: schema-output mapping identity and ranking

## Trigger

Use this note when maintaining static schema-output mapping detection in `scripts/audit_skill.py`, especially for flight-search-style schemas where one contract builder consumes another output object.

## Problem caught

A static detector falsely mapped:

- `cli/flights_cli/contracts/agent_report.v1.schema.json`
- to `cli/flights_cli/reporting/final_answer_contract.py`
- with scope `final_answer_contract`

The false positive came from weak code evidence: `build_user_answer_contract(agent_report)` accepted an `agent_report` parameter and read fields from it. That is consumer evidence, not exact schema identity evidence for `agent_report.v1.schema.json`.

At the same time, direct docs evidence was present and should win:

- command/flag: `python3 -m flights_cli --json route live-assemble SVX LED --agent-brief`
- output path: `data.agent_report`
- schema identity: `agent_report.v1.schema.json`

Expected static mapping:

- `mapping_kind`: `docs_explicit`
- `scope`: `cli_output`
- `output_name`: `data.agent_report`
- `command_hint`: includes `--agent-brief`
- `confidence`: `high`

## Detector rule

For `code_explicit`, require exact schema identity evidence in the same code file:

- exact schema filename, e.g. `agent_report.v1.schema.json`;
- exact schema version/name, e.g. `agent_report.v1`;
- exact `*_SCHEMA_RESOURCE` value matching the schema filename;
- exact `*_SCHEMA_VERSION` value matching the schema version;
- builder/validator/load function names only when the file also references the exact schema filename or version.

Do **not** treat these as exact schema identity:

- parameter names like `agent_report`;
- local variable names or field reads from `agent_report`;
- generic terms such as `report`, `answer`, `contract`, `schema`, `JSON`, or `output`.

## Ranking rule

When several candidates exist for the same schema, prefer:

1. `docs_explicit` + `scope=cli_output` + command hint present;
2. `report_contract`;
3. `code_explicit` with exact schema resource/version match;
4. `tests_explicit` with exact schema reference;
5. `naming_inference`.

A weak or consumer-only code candidate must not suppress a direct docs CLI-output mapping.

## Regression shape

Minimum future regression coverage:

1. `agent_report.v1.schema.json` + docs mentioning `--agent-brief`, `data.agent_report`, and exact schema filename produces high-confidence `docs_explicit` / `cli_output`.
2. `build_user_answer_contract(agent_report)` without `agent_report.v1` or `agent_report.v1.schema.json` does not produce high-confidence `code_explicit` / `final_answer_contract` for `agent_report.v1.schema.json`.
3. `flight_search_user_answer.v1.schema.json` still maps to `final_answer_contract` when the code file has exact `USER_ANSWER_SCHEMA_RESOURCE` and `USER_ANSWER_SCHEMA_VERSION` constants.
4. Helper-level test proves bare `agent_report` is not exact schema identity, while `agent_report.v1` and `agent_report.v1.schema.json` are.
5. Prefix and generic-name negatives: `agent_report.v1` must not match `agent_report.v10.schema.json`; generic unversioned names such as `output.schema.json` must not map from prose that merely says “output”.

## Verification commands used in the fix

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_schema_output_mappings -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import ast
for rel in [
    "scripts/audit_skill.py",
    "tests/test_schema_output_mappings.py",
]:
    ast.parse(Path(rel).read_text(encoding="utf-8"), filename=rel)
    print(f"syntax_ok {rel}")
PY
```

Also check the target skill tree for generated artifacts:

```bash
find "<runtime_skill>" \\
  \( -type d -name __pycache__ -o -type f -name '*.pyc' \) -print
```
