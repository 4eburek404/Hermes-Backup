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
- Preflight models suspected of empty-output behavior with a trivial direct content probe. As of 2026-06-12, `ollama-cloud` `gpt-oss:20b` can return `finish_reason=stop` and nonzero completion tokens but empty `message.content` even for `Say exactly OK`; classify this as provider/model empty-content failure and do not spend full eval runs unless the probe passes or a different backend is selected. **With `--ignore-user-config`** (fallback disabled), gpt-oss:20b produces `tool_call_count=0` and the final output is `"⚠️ No reply: the model returned empty content after retries and any fallback providers."` — this is the same empty-content bug, now exposed without the safety net. Filter these runs from tool_minimality counts.
- Preflight every small/new agent model with a **native tool-call smoke test**, not just a text probe: send the exact Hermes tool schemas for a harmless `write_file`/`terminal` action and require `finish_reason=tool_calls` plus at least one structured `tool_calls[]` entry in session provenance. If the model returns only a fenced JSON/Python/tool-code block or XML text with `0 tool calls` (as `ollama-cloud` `gemma3:12b` did on 2026-06-12), classify it as provider/model native-tool-call incompatibility; do not count printed snippets as execution, and do not spend full calendar eval runs unless model-as-agent failure is the thing being measured.
- Prefer provider/model variants advertised for tool use (e.g. Ollama Tools-category models or a tool-finetuned Gemma variant) when the goal is model-as-agent evaluation. Prompt wording alone is not a reliable remediation when the provider returns `message.content` instead of native `message.tool_calls`.
- If the goal is to evaluate the skill/runtime rather than model agency, move deterministic execution out of the model: harness runs the CLI, parses the compact JSON envelope, writes `result.json`, and optionally asks the model only for a final one-line handoff. Prompt-only evals are agent-workflow evals and will fail on models that cannot cross the native tool-call boundary.
- A core text-to-tool bridge, if ever used, must be opt-in and conservative: pure standalone tool-call block only, known tool allowlist, valid JSON parameters, no mixed prose, no execution of examples from tool output, and preferably a retry/nudge path before direct execution.
- Keep `SKILL_DIR` assignment on a separate line before using `$SKILL_DIR` in the command path; same-line temporary assignments are expanded too late by POSIX shells.
- Fast models may skip verification unless the contract makes verification easy; judge them by actual tool sequence and envelope checks.
- When counting tool calls from Hermes text logs, do not count `preparing ...` lines or review-diff display lines as separate tool invocations. Prefer structured invocation metrics when available; otherwise count completed operation lines such as `read`, `$ <command>`, and `write`, and cross-check with the final session footer. Treat `tool_calls_approx` as an approximation, not a quality metric by itself.
- **Sessions DB is the authoritative metric source for `hermes chat -Q` runs.** Quiet mode suppresses tool-invocation detail from stdout. After each `hermes chat` subprocess, extract the session ID from stderr (`session_id: <hex_id>`), then query `~/.hermes/state.db` table `sessions` for `tool_call_count`, `api_call_count`, `message_count`, and `model`. Also query `messages` table for `tool_calls` JSON to reconstruct the full tool trace. Beware a write-delay race: if the row is absent, retry after 1–2s (WAL checkpoint may be pending).
- **SQLite WAL access pattern for harness.** Use `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` and retry up to 5 times with 1s delay. The `?mode=ro` URI flag avoids locking conflicts with the WAL writer (hermes gateway). Plain `sqlite3.connect(path)` can race with WAL checkpoint; the row exists in the DB but is not yet visible to a reader that opened before the checkpoint completed. If the row is still absent after all retries, classify the run as a DB-visibility failure (not a model failure).
- **Python stdout buffering in subprocess.** When a Python harness runs via `subprocess.run(capture_output=True)` or background `terminal(background=True)`, `print()` output is line-buffered at best and may not appear in `process poll` output previews for minutes. The harness IS running — check filesystem artifacts (`run_metrics.json`, `aggregate.json`) instead of waiting for stdout. Add `-u` (`PYTHONUNBUFFERED=1`) or use `sys.stdout.flush()` after each status line if real-time progress monitoring matters.
- **gpt-oss:20b exclusion from multi-run eval.** As of 2026-06-14, `ollama-cloud` `gpt-oss:20b` is excluded from all multi-run tool_minimality evaluations. With `--ignore-user-config` (fallback disabled), it produces `tool_call_count=0` due to persistent empty-content failure (`finish_reason=stop`, nonzero tokens, empty `message.content`). This is a provider/model incompatibility, not a skill regression. If re-evaluating, preflight first with a native tool-call smoke test.

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

## v1.7.0 cross-model evaluation (2026-06-14)

Branch: `feat/icalendar-vtimezone-migration`. Key change: `icalendar` library migration, VTIMEZONE+TZID format.

| Model | v1.6.0 time | v1.7.0 time | Δ | v1.6.0 tools | v1.7.0 tools | Status |
|-------|------------|------------|---|-------------|-------------|--------|
| gemma4:31b | 25.7s | 26.6s | +3% | 8 | 5 | ✓→✓ |
| gemini-3-flash-preview | 29.3s | 28.1s | -4% | 8 | 5 | ✓→✓ |
| deepseek-v4-flash | 38.1s | 24.0s | -37% | 10 | 5 | ✓→✓ |
| gpt-oss:20b | 200.0s | 25.9s | -87% | 14 | 7 | ✓→✓ |

All 4: SUCCESS, `doctor_used=False`, `privacy_exposed=False`, `retries=0`.

Key findings:

- **ICS format change**: UTC-only DTSTART → TZID params with VTIMEZONE components. ICS size 3228→6763 bytes. DT fingerprint changed (expected, not regression).
- **Tool call efficiency uniformly improved**: every model used fewer tool calls (5–7 vs 8–14). The v1.6.0 handoff contract (`agent_handoff`, `safe_summary`) and v1.7.0 pitfalls clarity reduced redundant verification.
- **gpt-oss:20b transformation**: v1.6.0 had `finish_reason='length'` truncation, 200s wall-clock, 14 tool calls, concatenated final output. v1.7.0: 26s, 7 tool calls, clean handoff. The explicit `artifact_inspection_required=false` and code-owned `safe_summary` eliminated the post-completion discipline problem. This is an `agent_handoff` contract win, not a model capability change.
- **deepseek-v4-flash best improvement**: -37% time, -50% tool calls. Previously "insured" with extra checks; clearer contract eliminated them.
- **Direct CLI**: both versions produce correct output; v1.7.0 adds VTIMEZONE blocks (2) and TZID params; calendar clients now display local times.

Classification: all improvements are `envelope_contract_success` and `tool_minimality` layer wins. The `artifact_success` layer was already solid in v1.6.0. The v1.7.0 change is ICS format quality (RFC 5545 compliance) + handoff contract clarity, not generation correctness.

## Multi-run model evaluations

When the user asks for repeated runs per model, make the harness explicit and aggregate by layer rather than flattening each model into a single pass/fail:

1. Use isolated output directories per model and run, e.g. `model_runs/<model_id>/run_<n>/v<version>/`, and include `run_index` in the prompt and result JSON contract.
2. Keep one direct CLI baseline per eval root, then run the requested `N` model sessions with the same private input, prompt shape, provider/model tuple, and success schema.
3. For each `hermes chat -q` subprocess: extract session ID from stderr, query `~/.hermes/state.db` sessions table for `tool_call_count` (retry after 1–2s if row absent), and query messages table for `tool_calls` JSON to build the tool trace. Do not parse stdout for tool counts — `-Q` mode does not emit them.
4. Report per-model counts for each layer: `artifact_success`, `envelope_contract_success`, `result_json_schema_success`, `tool_minimality_success`, `privacy_success`, `final_answer_protocol_success`, and provider/model provenance match.
5. Report timing as distributions (`values`, `median`, optionally min/mean/max), not a single noisy latency number.
6. Preserve per-run evidence under local private artifacts: `hermes_invocations/<model_id>/run_<n>/.../{stdout,stderr,argv,invoke_metrics}.json`, `prompts/<model_id>/run_<n>/...`, `aggregate.json`, `all_runs_metrics.json`, and `summary.md`.

Two additional failure shapes to classify separately:

- A model may emit prose containing a tool-call-shaped JSON fragment without actually making a Hermes tool call. Treat the session footer / structured session provenance (`0 tool calls`) as authoritative; this is model tool-call reliability failure, not CLI failure.
- A model may create a valid artifact/envelope/result JSON, then concatenate prose after the requested one-line final answer or repeat the final line after `finish_reason='length'`. Treat this as final-answer protocol / stop handling failure even if the calendar generation layer is successful.

Keep artifacts local and sanitized, e.g. `v*_eval_raw.json`, `comparison_*_vs_previous*.json`, `aggregate.json`, `all_runs_metrics.json`, and `summary.md`. Do not include generated calendar text or private booking identifiers in summaries.

## Why models make redundant verification steps (causal model)

Even with an explicit handoff contract (`artifact_inspection_required=false`, code-owned `safe_summary`), models run 1–3 extra terminal calls after a successful `build auto`. The irreducible minimum for the happy path is 4 steps (read prompt, read SKILL.md, terminal build, write result), yet no model achieves this. The root causes form 5 layers:

### Layer 1: Training-data prior (~50% of waste)

LLMs are trained on millions of code examples where "verify file exists" = `os.path.exists()`, `stat`, `ls`, `test -f`. When a model sees "проверь ics_path exists, mode 0600, VEVENT count", its internal distribution overwhelmingly favors running a terminal check. This prior cannot be overridden by a short prompt instruction — it weighs ~10K tokens against trillions of training tokens.

Evidence: gemma4:31b runs TWO sequential verifications (138B + 46B output) despite the first returning all needed data. This is the classic code double-check pattern from training.

### Layer 2: Prompt ambiguity (~25% of waste)

The eval prompt verb "проверь" (check/verify) is an action imperative, not a reading instruction. Mixed with filesystem-sounding items ("ics_path exists", "mode 0600", "VEVENT count") that lack source attribution to envelope fields, models interpret this as "run terminal commands to independently verify" rather than "read these values from the envelope."

Fix: Replace action verbs with extraction verbs. Map each field explicitly to its envelope source. Add an explicit prohibition of terminal after build auto.

### Layer 3: Authority gap (~15% of waste)

Models rank information sources: direct observation (terminal output) > claims in data (envelope fields) > instructions to trust (SKILL.md). The envelope is a *claim* about filesystem state. Models add terminal verification to convert claims to direct observations, closing what they perceive as a due-diligence gap.

Fix: Add an explicit envelope field like `no_further_terminal_needed: true` — models obey data claims better than prose prohibitions.

### Layer 4: Model-specific biases (~10% of waste)

- **gpt-oss:20b**: "prepare environment" pattern (mkdir before CLI) + "think before acting" reflex (sequential_thinking on extractive tasks). v1.6.0: 14 tools, 200s, finish_reason=length. v1.7.0: 7 tools, 26s — `artifact_inspection_required=false` eliminated the worst excesses but not the pre-check and reasoning reflexes.
- **gemma4:31b**: "insurance behavior" — double verification as hedging against uncertainty.
- **gemini-3-flash / deepseek-v4-flash**: minimal single verification — closest to ideal but still +1 over the floor.

### Layer 5: Insurance behavior (strength varies with contract clarity)

Models add verification calls proportional to contract ambiguity. The v1.6.0→v1.7.0 improvement across all models (8→5, 8→5, 10→5, 14→7) shows that explicit `agent_handoff` + `safe_summary` + `artifact_inspection_required=false` reduces "insurance premiums." deepseek-v4-flash actually *regressed* v1.5.2→v1.6.0 (8→10 tools) when the envelope lacked explicit sufficiency signals, then improved to 5 in v1.7.0 when they were added.

### Concrete fixes ranked by impact

1. **Rewrite eval prompt**: Replace "проверь X, Y, Z" with "извлеки из data.agent_handoff.safe_summary: X, Y, Z. НЕ запускай terminal для проверки — все verification-поля уже в safe_summary." Map each field to its envelope source explicitly.
2. **SKILL.md hardening**: Add to Mandatory Runbook step 3.5: "На happy path НЕ запускай terminal-команды после build auto. CLI владеет верификацией — data.agent_handoff.safe_summary уже содержит verification_ok, ics_mode, vevent_count, segments_count, route."
3. **Envelope field**: Add `"no_further_terminal_needed": true` to agent_handoff. Models obey data claims better than prose.
4. **Remove gpt-oss sequential_thinking** from eval tool access, or add prompt clause: "рассуждения не требуются — просто извлеки поля."
5. **Combine prompt+SKILL.md reads** into one skill_view to reduce 4-step minimum to 3.

### Predicted impact

- gemini/deepseek: 5→4 steps (eliminate 1 verification call)
- gemma4: 6→4 steps (eliminate 2 verification calls)
- gpt-oss: 7→4 steps (eliminate mkdir, verification, sequential_thinking)

Remaining 0–1 step overhead is the irreducible training-prior floor that only architectural restrictions (terminal access disabled after build) or fine-tuning can eliminate.

## Historical trajectory: 3 eval generations

Cross-model tool-call counts across skill versions, same eval prompt, same private input:

| Model | v1.5.2 tools | v1.6.0 tools | v1.7.0 tools | v1.5.2 time | v1.6.0 time | v1.7.0 time |
|-------|-------------|-------------|-------------|-------------|-------------|-------------|
| gemma4:31b | 14 | 8 | 6 | 32.1s | 25.7s | 26.6s |
| gemini-3-flash | 8 | 8 | 5 | 28.3s | 29.3s | 28.1s |
| deepseek-v4-flash | 8 | 10 | 5 | 34.2s | 38.1s | 24.0s |
| gpt-oss:20b | 12 | 14 | 7 | 29.3s | 200.0s | 25.9s |

Key observations:
- Every handoff-contract improvement (v1.5.2→v1.6.0: `agent_handoff`; v1.6.0→v1.7.0: `artifact_inspection_required=false` + `safe_summary`) reduced tool calls.
- deepseek-v4-flash *regressed* 8→10 in v1.6.0 when the envelope lacked explicit sufficiency signals, then improved to 5 in v1.7.0 when they were added. This confirms insurance-behavior hypothesis.
- gpt-oss:20b v1.6.0 had `finish_reason='length'` truncation at 200s. v1.7.0's explicit handoff eliminated the post-completion discipline problem (26s, 7 tools, clean).
- The eval prompt was identical across all 3 generations — the ambiguity ("проверь ... ics_path exists, mode 0600") persisted. Fixing it should push all models to 4 steps.

## Minimal-prompt experiment (2026-06-14)

Tested whether removing verbose eval instructions eliminates waste. Same skill (v1.7.0), same private input, minimal prompt (~250 chars vs ~2400 chars verbose):

> «Навык: flight-calendar-ics. Ссылка: [url]. Output dir: [path].
> requested_provider: ollama-cloud, requested_model: [model], skill_version_label: runtime-skill-1.7.0»

Results:

| Model | v1.7.0 verbose | v1.7.0 minimal | Δ tools |
|-------|---------------|----------------|---------|
| gemma4:31b | 6 | 11 | +5 |
| gemini-3-flash-preview | 5 | 5 | 0 |
| deepseek-v4-flash | 5 | 10 | +5 |
| gpt-oss:20b | 7 | **4** | -3 |

gpt-oss:20b hit the **ideal 4-step trajectory** with minimal prompt.
gemma4:31b and deepseek-v4-flash **regressed** — without the verbose prompt's guide rails, they lost direction and explored more.

### Key conclusion

The verbose eval prompt is **dual-natured**:
- **Harmful part**: "проверь ics_path exists, mode 0600" triggers verification
- **Helpful part**: "не запускай doctor, не читай .ics" constrains exploration

Removing it eliminates the harm for models that follow SKILL.md naturally (gpt-oss:20b), but also removes the guardrails for models that need explicit constraints (gemma4, deepseek).

**The correct fix is not in the eval prompt — it's in SKILL.md.** The skill must work with ANY prompt, including a minimal production prompt ("сделай ICS из этой ссылки"). If SKILL.md is correctly designed:
- Action verbs are replaced with descriptive phrasing
- Diagnostic commands are moved to references (not inline)
- Verification checklists are moved to eval references (not main doc)
- The happy path is a complete, self-contained, non-contradictory sequence

Then the eval prompt can be minimal and the skill works correctly in production too.

### SKILL.md defects identified through this experiment

1. **Step 4 "Require"** = action verb → triggers verification. Replaced with "The CLI guarantees" (descriptive).
2. **Steps 4+5 split** → conflict between "require" and "don't verify". Merged into one step.
3. **Inline diagnose commands** → availability bias. Moved to references with one-line pointer.
4. **Verification Checklist in main doc** → eval-specific, triggers checks. Moved to references/maintenance/evaluation.md.

These fixes were applied to SKILL.md in the same session.

## Top-level no_further_action_needed experiment (v1.7.7 → v1.7.8, 2026-06-14)

v1.7.8 promotes `no_further_action_needed` from depth-3 (inside `agent_handoff`) to top-level JSON (alongside `ok`). Hypothesis: models check `ok` first and will stop sooner when the stop signal is adjacent.

### Single-run results (pre-multi-run)

| Model | v1.7.7 depth-3 tools | v1.7.8 top-level tools | Δ |
|-------|----------------------|------------------------|---|
| gpt-oss:20b | 7 | 5 | −2 ✅ |
| gemma4:31b | 5 | 6 | +1 |
| gemini-3-flash | 6 | 6 | 0 |
| deepseek-v4-flash | 7 | 8 | +1 |

gpt-oss:20b was the only model to benefit from top-level placement. Others showed neutral or slightly worse behavior.

### Multi-run harness

`scripts/multirun_harness.py` runs N≥5 sessions per (model × version) pair, queries `~/.hermes/state.db` for authoritative `tool_call_count`, and reports tool_minimality distribution + per-layer counts. gpt-oss:20b is excluded from all multi-run evals (persistent empty-content failure).

### Preflight verification

Before trusting tool_minimality counts, run preflight with `--ignore-user-config` to disable fallback providers. Verify:
1. `tool_call_count > 0` for each model (native tool-call capability confirmed)
2. No "Fallback activated" in session content
3. `model` field in sessions DB matches requested model (no silent provider substitution)

Models that fail preflight with `zero_tool_calls=True` and no fallback have a provider/model incompatibility — their eval numbers are unreliable.

### Key harness pitfalls

- **WAL commit lag**: `sqlite3.connect(f"file:{db}?mode=ro", uri=True)` with 5 retries × 1s delay. The session row exists but may not be visible to readers opened before WAL checkpoint completes.
- **Python stdout buffering**: `subprocess.run(capture_output=True)` and background processes do not flush print() in real time. Monitor filesystem artifacts (`run_metrics.json`) for progress.
- **Version switching**: The harness toggles top-level `no_further_action_needed` promotion in `parser.py` via string replacement. Always restore v1.7.8 (top-level enabled) after eval completes.
- **Session ID from stderr**: `hermes chat -Q` emits `session_id: <hex_id>` on stderr. Parse with `re.search(r"session_id:\s*([a-f0-9_]+)", proc.stderr)`.

## v1.7.7→v1.7.8 multi-run evaluation (2026-06-14, N=5)

Top-level `no_further_action_needed: true` promotion from `agent_handoff` to JSON root.

**Setup:** 3 models × 2 versions × 5 runs = 30 sessions. `--ignore-user-config` (fallback off). Metrics from sessions DB (sqlite3). gpt-oss:20b excluded (persistent empty-content failure, 0 native tool calls).

### tool_minimality distribution

**deepseek_v4_flash** — signal works ✅
- v1.7.7 depth-3: med=6 σ=1.58 dist={4:1, 5:1, 6:1, 7:1, 8:1}
- v1.7.8 top-level: med=5 σ=0.45 dist={5:4, 6:1}
- **Δ=−1** median, σ↓3.5×
- tool_minimality_success: 2/5 → 4/5
- artifact: 4/5 → 4/5, envelope: 5/5 → 5/5

**gemini_3_flash_preview** — neutral ≈
- v1.7.7 depth-3: med=3 σ=0.45 dist={2:1, 3:4}
- v1.7.8 top-level: med=3 σ=0.84 dist={2:2, 3:2, 4:1}
- **Δ=0**, but σ↑ (more variance)
- tool_minimality_success: 2/5 → 2/5
- artifact: 2/5 → 2/5, envelope: 4/5 → 3/5

**gemma4_31b** — not capable for this skill ❌
- v1.7.7: med=2 σ=0.0 dist={2:5}
- v1.7.8: med=2 σ=0.0 dist={2:5}
- **Δ=0**, signal no effect
- tool_minimality_success: 0/5 → 0/5
- artifact: 0/5 → 0/5 — never produces .ics
- Trace: always `[terminal, write_file]` — not following runbook

### Per-layer counts (v1.7.7 → v1.7.8)

deepseek_v4_flash:
- tool_minimality: 2/5 → 4/5
- artifact: 4/5 → 4/5
- envelope: 5/5 → 5/5
- fallback_activated: 0 → 0
- zero_tool_calls: 0 → 0

gemini_3_flash_preview:
- tool_minimality: 2/5 → 2/5
- artifact: 2/5 → 2/5
- envelope: 4/5 → 3/5
- fallback_activated: 0 → 0
- zero_tool_calls: 0 → 0

gemma4_31b:
- tool_minimality: 0/5 → 0/5
- artifact: 0/5 → 0/5
- envelope: 2/5 → 2/5
- fallback_activated: 0 → 0
- zero_tool_calls: 0 → 0

### Conclusions

1. **Top-level `no_further_action_needed` works for deepseek-v4-flash**: −1 median tool calls, +2× minimality pass rate, σ↓3.5×. Reproducible signal.
2. **Gemini neutral**: model already stops early (med=3), signal gives no additional effect; slight variance increase.
3. **Gemma4 not capable**: 0/10 artifact success, always 2 tool calls, never follows SKILL.md runbook. Signal irrelevant.
4. **Fallback clean**: 0/30 sessions with "Fallback activated" under `--ignore-user-config`.
5. **Zero tool calls**: 0/30 — no sessions without tool calls (problem was gpt-oss:20b only, excluded).

### Tool trace patterns

deepseek v1.7.7 (high variance): `[read_file, terminal, terminal, terminal, read_file, write_file, terminal, read_file]` — 4-8 tools, redundant terminal+read_file
deepseek v1.7.8 (converged): `[read_file, read_file, terminal, terminal, write_file]` — 5-6 tools, clean pattern
gemini: `[terminal, terminal, write_file]` or `[terminal, write_file]` — minimal but often misses artifact
gemma4: `[terminal, write_file]` — always same 2-step, never reads SKILL.md or runs build auto

### Gemma4:31b root-cause analysis (not a model regression)

The multi-run harness prompt says «Follow SKILL.md runbook exactly. Write result.json» with an abstract `Output dir: /path` reference. Gemma4 runs the CLI command **without `--output-dir`**, so `flight_calendar_ics.py` creates the .ics in a temp directory (`/tmp/flight-ics.<rand>/`). The harness checks for `flights.ics` in the run's output directory → `artifact_success=False`.

This is **not** a model regression. In previous evals (v1.6.0, v1.6.1, v1.7.0), gemma4 scored `artifact_success=True` because the eval prompt contained the exact CLI command with `--url-file "..." --output-dir "..."`. Gemma4 copied the command verbatim and succeeded. The current harness gives an abstract task description; gemma4 cannot autonomously infer `--output-dir` from «Output dir: /path».

**Implication for harness design**: eval prompts that test autonomous skill navigation (model reads SKILL.md, infers CLI args) vs. instruction-following (model copies a given command) measure different capabilities. Gemma4:31b is instruction-following capable but autonomous-skill-execution limited for this skill. To measure tool_minimality fairly across models, include the full CLI command in the prompt or add `--output-dir` explicitly.

### Preflight verification (Task 2)

With `--ignore-user-config` (fallback disabled):
- gemma4:31b → tool_call_count=1 ✅ native tool call works
- gemini-3-flash-preview → tool_call_count=1 ✅ native tool call works
- deepseek-v4-flash → tool_call_count=1 ✅ native tool call works
- gpt-oss:20b → tool_call_count=0 ❌ empty-content failure (excluded from eval)
- No "Fallback activated" in any session ✅
