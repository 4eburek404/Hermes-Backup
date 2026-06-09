# Model Evaluation for Flight Calendar ICS

Use this when comparing changes to the CLI/skill contract across multiple agent models. Keep this reference free of concrete booking URLs, PNRs, passenger names, ticket/document/contact/payment data, and generated deep-links.

## Purpose

Measure agent behavior around the CLI contract, not just raw CLI speed. The direct CLI should be fast; model variance usually comes from agent/tool-loop behavior: extra reads, diagnostics, verification scripts, retries, and final reporting.

## Stable Evaluation Pattern

1. **Record provenance.** Capture branch, commit short/subject, clean/dirty git status, skill source path, CLI path, and whether runtime skill sync was deliberate.
2. **Validate the effective model/provider.** After every subagent/session, compare requested `provider/model` with actual session metadata (`session.model`, `base_url`). Mark mismatches invalid or bucket them separately; do not attribute behavior to a model that did not actually run.
   - If the model is served by Ollama Cloud, request `provider=ollama-cloud` directly and put the concrete Ollama model name in `model` (for example `deepseek-v4-pro`, `glm-5.1`, `gemini-3-flash-preview`, `gemma4:31b`). Do not label these rows as native `deepseek`, `zai`, or `gemini`; native providers may fail auth and fall back to another configured provider.
3. **Use the same private evidence.** Store credential-bearing URLs in a private file such as `/tmp/flight_ics_private_input/url.txt` with mode `0600`. Do not print or read the file into model-visible output.
4. **Use the one-command happy path.** For carrier URLs and canonical itinerary JSON, the evaluator should read `SKILL.md` once, then run exactly one normal generation command:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
   ```

   or:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
   ```

   Do not run `doctor`, explicit `build <route>`, source inspection, carrier-reference inspection, or broad scanner commands unless the eval explicitly measures diagnostics/failure handling.

   In automated prompts, prefer literal absolute command strings (for example `python "/abs/skill/scripts/flight_calendar_ics.py" --json build auto --url-file "/private/source-url.txt" --output-dir "/abs/out"`). Do not ask agents to combine temporary same-line shell assignments with `$SKILL_DIR` in the command path: POSIX expands `$SKILL_DIR` before `SKILL_DIR=...` is applied to that command, causing repeatable `/scripts/flight_calendar_ics.py` failures.

5. **Validate envelope, not private content.** Require:
   - `schema_version == flight-calendar-ics-cli.v1`
   - `ok is true`
   - `command == build`
   - `data.route` is expected
   - `data.route_detection.mode == auto`
   - `data.segments_count >= 1`
   - `data.verification.ok is true`
   - `data.ics_path` exists
   - private artifacts intended for private use are mode `0600`

   For VEVENT counts, file mode, byte size, or timestamp-shape checks, use count-only terminal/Python commands that print only numbers/booleans/fingerprints. Do **not** call `read_file` on generated `.ics` files during eval: calendar descriptions can contain PNR/passenger/booking details, and reading the file injects them into the persisted model session even if the final report redacts them.

6. **Check private-input exposure narrowly.** This is not a generic secret scanner. For eval reporting, check only that known private input values from the test fixture are absent from stdout/stderr/result/envelope/report. Prefer exact known-value checks or hashed manifests. Do not flag safe labels such as field names, carrier names, route names, or documentation words.

7. **Compare against prior runs.** Track success, elapsed seconds, tool calls, selected command, route, route-detection mode, envelope verification, private-input exposure status, `doctor` usage from session/tool trace (not model self-report), retries, and effective model/provider match.

8. **For branch comparisons, run two layers.** Use the same private input and requested provider/model for both branches. First run a direct CLI smoke per branch to isolate product latency and output contract. Then run the model-driven Hermes eval per branch to measure agent/tool-loop behavior. Normalize into one comparison artifact with branch commit, effective model/base URL, model wall-clock, direct CLI elapsed, tool calls, terminal commands, `doctor` usage, privacy sentinel exposure, result paths, and `.ics` fingerprints.

9. **Verify actual tool commands structurally.** When checking `doctor` usage, retries, or extra diagnostics, parse the persisted session `messages[*].tool_calls[*].function` records and inspect actual `terminal` command arguments. Do not grep the whole session JSON; it contains tool schemas, prompts, and skill text that can create false positives.

## Why Not Broad Credential Grep Here

Broad substring/keyword/entropy searches are the wrong tool for this eval because they confuse labels with secrets. In this skill, words such as `pnr`, `token`, `key`, `route_detection`, and carrier field names are often safe metadata, not leaked credential values.

Industry pattern from current public docs:

- GitHub secret scanning relies on provider patterns and validation; for some pattern pairs it requires both parts in the same file to reduce false positives.
- GitHub treats generic secret detection separately and expects careful manual triage because generic detections have more false positives.
- `detect-secrets` uses a baseline plus audit/allowlisting workflow so known false positives do not keep breaking future runs.

So for this skill:

- Use exact fixture/sentinel non-exposure checks in CLI tests and eval harnesses.
- Use real DevSecOps tools such as GitHub secret scanning, Gitleaks, TruffleHog, or `detect-secrets` only as a separate security pipeline with validation/baselines/allowlists/manual triage.
- Do not embed a homegrown broad secret scanner into the model-eval success criteria.

## Recommended Comparison Fields

- requested provider/model
- effective session model/base URL
- model match: yes/no
- elapsed seconds
- success / failure reason
- selected command
- route
- route-detection mode
- envelope verification ok
- private-input exposure ok
- tool calls
- `doctor` used: yes/no
- retries or failed pre-CLI commands
- previous elapsed/success/tool calls
- delta seconds / percent

Session IDs and output directories may be kept in local JSON artifacts for auditability, but omit them from compact chat summaries unless needed for troubleshooting.

## Interpreting Results

- Direct CLI elapsed indicates CLI overhead.
- Model wall-clock reflects agent/tool-loop behavior plus provider/network variance.
- One run per model is directional, not statistically stable.
- A slower result is not a CLI regression unless direct CLI smoke also regressed.
- If a row's effective model/provider does not match the requested label, the row is invalid for model comparison.

Typical pattern:

- Fast/compliant models read `SKILL.md`, run `build auto`, verify envelope, and stop.
- Cautious or confused models may over-audit when the prompt mentions diagnostics, broad credential grep, route-detection internals, or maintenance.
- If the successful envelope is already verified, extra source/reference/`.ics` inspection is agent-loop overhead, not product value.

## Fast-Path Eval Prompt Clause

```text
Read SKILL.md once. Run exactly one `--json build auto --url-file <private-file>`. Verify only envelope/path/mode/counts/route_detection. Do not run doctor, inspect source/references/generated .ics content, run broad secret scanners, or patch the skill unless build/verification fails. Stop after successful envelope verification. Report actual session model/provider from session metadata.
```

## Pitfalls

- Comparing requested model labels instead of actual session model/provider.
- Requesting Ollama Cloud-hosted DeepSeek/GLM/Gemini/Gemma via native provider names instead of `ollama-cloud`, then measuring a fallback row as if it were the requested model.
- Treating eval as automatic permission to run `doctor`.
- Detecting `doctor` usage by grepping the whole persisted session JSON. Tool schemas, skill text, or the eval prompt may mention `doctor`; parse assistant `tool_calls` and inspect actual terminal command strings instead.
- Treating keyword hits such as `pnrKey` field labels as leaked secrets.
- Letting subagents dump private URL or `.ics` descriptions into stdout.
- Letting subagents verify VEVENT by `read_file` on generated `.ics`; use count-only terminal/Python checks instead, then scan persisted session text for exact private sentinels.
- Reporting full session narratives instead of distilled metrics.
- Interpreting provider wall-clock variance as CLI performance without a direct CLI smoke test.
- Prompting Codex with a same-line `SKILL_DIR=... python "$SKILL_DIR/..."` command; use literal absolute paths or separate `export` lines.
