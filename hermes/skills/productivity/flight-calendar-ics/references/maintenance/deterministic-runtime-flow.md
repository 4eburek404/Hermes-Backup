# Deterministic runtime flow for weak/non-tool models

Use this when evaluating or operating `flight-calendar-ics` with models that may not reliably emit native Hermes tool calls.

## Core distinction

There are two different questions:

1. **Skill/runtime correctness** — does the code-owned CLI generate and verify a calendar artifact?
2. **Model-as-agent ability** — can a model choose and emit native Hermes `tool_calls` to run the workflow?

Do not flatten these into one pass/fail. A model can fail tool calling while the skill/runtime is healthy.

## Production/user flow for weak models

For weak or non-tool-call-native models, do not ask the model to call `terminal`/`write_file` for the happy path. Use a deterministic handler/wrapper:

```text
user input -> private source file -> flight_calendar_ics.py --json build auto -> parse JSON handoff -> deliver MEDIA + safe_summary
```

The model, if present, should only receive the code-owned safe summary and may write a human-readable caption. It should not see private booking URLs/PNR/passenger/ticket/contact/payment values and should not be responsible for shell execution, artifact validation, or result JSON normalization.

## Evaluation pattern

For skill/runtime regression:

1. Copy the same private input into a new run-private directory with mode `0600`; compare only bytes/hash equality, never print the value.
2. Run the skill-owned CLI directly for each run:
   ```bash
   python3 -B "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file "$PRIVATE_URL_FILE" --output-dir "$RUN_OUT"
   ```
3. Parse stdout as the compact JSON handoff.
4. Require: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, `command=build`, `data.agent_handoff.ready=true`, `artifact_inspection_required=false`, `safe_summary.verification_ok=true`, `MEDIA:` handoff, expected segment/event counts, `.ics` mode `0600`, no placeholders, and privacy scan clean.
5. Write per-run `result.json`, then aggregate counts by layer: `cli_return_success`, `envelope_contract_success`, `artifact_success`, `privacy_success`, `normalized_success`.

For model-as-agent evaluation, run a native tool-call smoke test first. If the session footer/provenance reports `0 tool calls` while the assistant printed a pseudo tool call as text, classify it as model/provider native-tool-call failure and do not attribute it to the calendar skill.

## UX pitfall

Do not treat a terse user message such as `3.` as sufficient approval to write files or run a new evaluation unless the numbered choice is unambiguous and current. When in doubt, explain the interpretation first or ask a short clarification. This is especially important after presenting multiple architecture options.

## Reporting

Report status by layer:

- `flight-calendar-ics CLI/runtime`: generated artifact and handoff?
- `model tool-calling`: native `tool_calls` emitted?
- `delivery/final response`: one-line handoff or caption correct?

A good concise summary is:

```text
Skill/runtime: PASS (3/3 deterministic CLI runs). Model-as-agent: FAIL for <model> (0 native tool calls). Cause: provider/model emitted textual pseudo tool call, not `message.tool_calls`.
```
