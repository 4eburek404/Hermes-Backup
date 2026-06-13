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
- Do not treat a provider fallback as a model-quality result. For strict named-model evals, disable user-configured fallback (for CLI harnesses use `--ignore-user-config` or a temp config with `fallback_providers: []`) or mark any `Fallback activated: <requested> → <other>` log line as a run failure. The session table may still show the requested model, so scan `agent.log`/stdout for fallback evidence before counting provider/model provenance as matched.
- Preflight models suspected of empty-output behavior with a trivial direct content probe. As of 2026-06-12, `ollama-cloud` `gpt-oss:20b` can return `finish_reason=stop` and nonzero completion tokens but empty `message.content` even for `Say exactly OK`; classify this as provider/model empty-content failure and do not spend full eval runs unless the probe passes or a different backend is selected.
- Preflight every small/new agent model with a **native tool-call smoke test**, not just a text probe: send the exact Hermes tool schemas for a harmless `write_file`/`terminal` action and require `finish_reason=tool_calls` plus at least one structured `tool_calls[]` entry in session provenance. If the model returns only a fenced JSON/Python/tool-code block or XML text with `0 tool calls` (as `ollama-cloud` `gemma3:12b` did on 2026-06-12), classify it as provider/model native-tool-call incompatibility; do not count printed snippets as execution, and do not spend full calendar eval runs unless model-as-agent failure is the thing being measured.
- Prefer provider/model variants advertised for tool use (e.g. Ollama Tools-category models or a tool-finetuned Gemma variant) when the goal is model-as-agent evaluation. Prompt wording alone is not a reliable remediation when the provider returns `message.content` instead of native `message.tool_calls`.
- If the goal is to evaluate the skill/runtime rather than model agency, move deterministic execution out of the model: harness runs the CLI, parses the compact JSON envelope, writes `result.json`, and optionally asks the model only for a final one-line handoff. Prompt-only evals are agent-workflow evals and will fail on models that cannot cross the native tool-call boundary.
- A core text-to-tool bridge, if ever used, must be opt-in and conservative: pure standalone tool-call block only, known tool allowlist, valid JSON parameters, no mixed prose, no execution of examples from tool output, and preferably a retry/nudge path before direct execution.
- Keep `SKILL_DIR` assignment on a separate line before using `$SKILL_DIR` in the command path; same-line temporary assignments are expanded too late by POSIX shells.
- Fast models may skip verification unless the contract makes verification easy; judge them by actual tool sequence and envelope checks.
- When counting tool calls from Hermes text logs, do not count `preparing ...` lines or review-diff display lines as separate tool invocations. Prefer structured invocation metrics when available; otherwise count completed operation lines such as `read`, `$ <command>`, and `write`, and cross-check with the final session footer. Treat `tool_calls_approx` as an approximation, not a quality metric by itself.

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

## Monitoring remote/Desktop-launched evals from Telegram

When the user asks from Telegram "how is the Desktop/Mac eval going?", treat the shared Hermes session store and local process table as evidence, but do not require the originating TUI session to have a final assistant message before reporting progress.

Evidence sequence:

1. Locate the originating `tui`/Desktop session by recency or topic and read its kickoff to confirm the requested scope.
2. Check the evaluator process and children (`flight_ics_eval*_harness.py`, `hermes chat --source flight-ics...`) to distinguish running, blocked, and completed states.
3. Identify the run root from the harness argv/stdout/path convention, then inspect only sanitized evaluator artifacts: `run_metadata.json`, `direct_cli/**/direct_metrics.json`, `hermes_invocations/**/invoke_metrics.json`, `aggregate.json`, and `summary.md`.
4. Count completion from structured metrics, not from the Desktop UI state. A harness can finish and write `aggregate.json`/`summary.md` while the parent TUI worker is still alive or the session transcript still shows only the kickoff user message.
5. Report status-first: process state, `completed/expected`, run root, direct CLI baseline, per-model success counts, and the first causal layer for failures. Keep booking URL/PNR/passenger/ticket/contact/payment data and generated ICS text out of chat.

Pitfall: if the parent TUI session is still running with no final response, do not say the eval is lost or unfinished when the run root already has complete aggregate files. Say the evaluator completed and note that UI/session final delivery may lag or have failed separately.

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

If an eval prompt must ask the model to produce `result.json`, explicitly say to derive handoff fields from the compact JSON stdout after a successful envelope: `handoff_media = data.agent_handoff.media`; `ics_exists = true` from `data.agent_handoff.ready=true`, `safe_summary.verification_ok=true`, and a `MEDIA:` prefix (do **not** require `data.ics_path`); `ics_mode` and `vevent_count` from `data.agent_handoff.safe_summary` with `data.verification` only as a fallback. Do not run `stat`, `ls`, `grep`, `cat`, `test`, open `.ics`, or run `doctor` on the happy path.

For qualitative reports, do not stop at broad labels like "provider output handling". Explain the measured causal chain: e.g. CLI completed in ~1s and wrote a valid artifact; the model then corrupted the final one-line protocol and hit `finish_reason='length`, so the failure is post-completion handoff, not calendar generation.

## Multi-run model evaluations

When the user asks for repeated runs per model, make the harness explicit and aggregate by layer rather than flattening each model into a single pass/fail:

1. Use isolated output directories per model and run, e.g. `model_runs/<model_id>/run_<n>/v<version>/`, and include `run_index` in the prompt and result JSON contract.
2. Keep one direct CLI baseline per eval root, then run the requested `N` model sessions with the same private input, prompt shape, provider/model tuple, and success schema.
3. Report per-model counts for each layer: `artifact_success`, `envelope_contract_success`, `result_json_schema_success`, `tool_minimality_success`, `privacy_success`, `final_answer_protocol_success`, and provider/model provenance match.
4. Report timing as distributions (`values`, `median`, optionally min/mean/max), not a single noisy latency number.
5. Preserve per-run evidence under local private artifacts: `hermes_invocations/<model_id>/run_<n>/.../{stdout,stderr,argv,invoke_metrics}.json`, `prompts/<model_id>/run_<n>/...`, `aggregate.json`, `all_runs_metrics.json`, and `summary.md`.

Two additional failure shapes to classify separately:

- A model may emit prose containing a tool-call-shaped JSON fragment without actually making a Hermes tool call. Treat the session footer / structured session provenance (`0 tool calls`) as authoritative; this is model tool-call reliability failure, not CLI failure.
- A model may create a valid artifact/envelope/result JSON, then concatenate prose after the requested one-line final answer or repeat the final line after `finish_reason='length'`. Treat this as final-answer protocol / stop handling failure even if the calendar generation layer is successful.

Keep artifacts local and sanitized, e.g. `v*_eval_raw.json`, `comparison_*_vs_previous*.json`, `aggregate.json`, `all_runs_metrics.json`, and `summary.md`. Do not include generated calendar text or private booking identifiers in summaries.
