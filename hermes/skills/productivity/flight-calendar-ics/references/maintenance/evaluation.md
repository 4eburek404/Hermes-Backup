# Evaluation and Cross-Model Review

Audience: maintainers only. This file is never part of an agent generation or failure path.

This file consolidates model-evaluation, provider, and shell pitfalls for this skill.

## Evaluation default

When evaluating normal generation behavior, every model gets the same privacy-safe task and should use the one-command happy path:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
```

Use `doctor`, `diagnose ...`, or carrier references only if diagnostics are explicitly under evaluation or the build fails.

## Evidence requirements

For named-model review:

- obtain an answer from each named model;
- save evidence with model name, status, command sequence, and sanitized output path;
- synthesize across model answers rather than replacing missing model output with the agent's own answer;
- classify failures by layer: provider identity, shell expansion, prompt state, CLI contract, route detection, schema validation, privacy check, or environment limitation.

## Provider and shell pitfalls

- Verify effective provider/model identity from evidence, not display name alone.
- Do not treat a provider fallback as a model-quality result.
- Keep `SKILL_DIR` assignment on a separate line before using `$SKILL_DIR` in the command path; same-line temporary assignments are expanded too late by POSIX shells.
- Fast models may skip verification unless the contract makes verification easy; judge them by actual tool sequence and envelope checks.

## Privacy rules for evals

- Use private source files for credential-bearing sources.
- Store raw model/tool evidence only in local private artifacts when necessary.
- Redact private source values and generated calendar text from reports.
- Fixture data must be synthetic.

## Recommended comparison fields

- model/provider/effective model;
- first command run;
- whether `build auto` was used;
- whether diagnostics were used and why;
- envelope verification result;
- privacy violations count/type, with no raw values;
- final deliverable status.

## Runtime version re-evaluation pattern

When re-running a previous model evaluation against a new skill version, keep the evaluation comparable before judging model quality:

1. Reuse the same private input file by copying it into the new run's private directory with mode `0600`; compare only bytes/hash equality, never print the value.
2. Capture a direct CLI baseline for the current version before model runs:
   - `--json build auto --url-file <private-url-file> --output-dir <direct-cli-out>`
   - record elapsed time, route, segment count, `verification.ok`, `.ics` mode, `VEVENT` count, UTC `DTSTART/DTEND`, placeholder count, and a timestamp-only fingerprint.
3. Run each model with the same prompt shape, output directory layout, and success schema as the previous run. Include new contract fields such as `agent_handoff.ready` and `artifact_inspection_required` when the skill version exposes them.
4. Normalize success from evidence, not the model's final status line alone: require valid `result.json`, successful envelope fields, expected route/segment/event counts, `.ics` mode `0600`, UTC timestamps, no placeholders, and no privacy-pattern hits in stdout/stderr/result JSON.
5. Compare previous vs current per model: success, elapsed, approximate tool calls, route, segment/event counts, `.ics` bytes, timestamp fingerprint, privacy hits, and provider/model warnings.
6. Attribute latency regressions to the correct layer. If direct CLI is fast and unchanged but a model run is slow or repeats the final answer after `finish_reason='length'`, classify it as provider/model final-output/stop handling rather than a skill regression. Be concrete: cite the CLI elapsed time, session duration, truncation warnings, final-line corruption, and the first layer where the contract broke.

## Evaluating the evaluator, not just the skill

A more machine-readable CLI envelope only improves model evals when a deterministic consumer reads it. If the prompt asks the model to parse the envelope, verify files, normalize fields, write `result.json`, and obey a one-line final protocol, the run is still testing the LLM agent as workflow engine.

When interpreting results, split the score into separate layers:

- `artifact_success`: `.ics` exists, expected bytes/event counts/timestamp fingerprint, privacy-safe mode.
- `envelope_contract_success`: `schema_version`, `ok`, `command`, `verification.ok`, `agent_handoff.ready`, and `artifact_inspection_required=false` are correct.
- `result_json_schema_success`: model- or wrapper-written result has canonical types/values (`0600` vs `600`, numeric retry count, elapsed when required).
- `tool_minimality`: successful happy path should be `read SKILL.md` + one `build auto`; extra `stat`, `ls`, `grep`, `cat`, or `doctor` are model/eval-surface behavior unless the build failed.
- `final_answer_protocol_success`: final response is exactly the requested one-line handoff and stops.
- `wall_time_overhead`: compare session duration to direct CLI/build-command elapsed; if >95% of time is agent loop, don't present CLI optimization as end-to-end speedup.

Prefer a programmatic evaluator for version comparisons:

```text
CLI envelope -> deterministic parser/schema validator -> result.json -> model final one-liner only
```

When a prompt-only fix removes extra filesystem inspections but final-protocol failures or truncation remain, optimize the code-owned handoff before adding more prose. The durable pattern is:

1. Keep the full diagnostic envelope in `envelope.json`, but expose a compact happy-path handoff surface for agents/evals.
2. Put already-normalized delivery fields in code (`MEDIA:...`, safe caption/summary, `artifact_inspection_required=false`, `verification_ok=true`).
3. Canonicalize values in the CLI/schema, not in prompts or evaluators; e.g. file modes should be emitted as the required public form (`0600`) if that is what result schemas compare.
4. Make the model copy a ready delivery field or one-liner rather than compose it from multiple envelope fields.

This is especially important for slow or truncation-prone models: if direct CLI elapsed time is ~1s and the artifact/envelope are valid, remaining wall time and final-line corruption are model/evaluator surface issues. Shrinking stdout and making the final response code-owned reduces token pressure and distinguishes skill correctness from model workflow reliability.

If an eval prompt must ask the model to produce `result.json`, explicitly say to derive `ics_exists`, `ics_mode`, and `vevent_count` from `data.verification` / `data.agent_handoff.safe_summary` after a successful envelope, and not to run `stat`, `ls`, `grep`, `cat`, open `.ics`, or run `doctor`.

For qualitative reports, do not stop at broad labels like "provider output handling". Explain the measured causal chain: e.g. CLI completed in ~1s and wrote a valid artifact; the model then corrupted the final one-line protocol and hit `finish_reason='length`, so the failure is post-completion handoff, not calendar generation.

Keep artifacts local and sanitized, e.g. `v*_eval_raw.json`, `comparison_*_vs_previous*.json`, and `summary.md`. Do not include generated calendar text or private booking identifiers in summaries.
