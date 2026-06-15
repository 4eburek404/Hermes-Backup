# Evaluation and Cross-Model Review

Audience: maintainers only. This file is never part of an agent generation or failure path.

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
- Do not treat a provider fallback as a model-quality result. For strict named-model evals, disable user-configured fallback (for CLI harnesses use `--ignore-user-config` or a temp config with `fallback_providers: []`) or mark any `Fallback activated` log line as a run failure.
- Preflight models suspected of empty-output behavior with a trivial direct content probe. As of 2026-06-12, `ollama-cloud` `gpt-oss:20b` can return `finish_reason=stop` with empty `message.content`; classify as provider/model empty-content failure and do not spend full eval runs unless the probe passes.
- Preflight every small/new agent model with a **native tool-call smoke test** (see below).
- Keep `SKILL_DIR` assignment on a separate line before using `$SKILL_DIR` in the command path; same-line temporary assignments are expanded too late by POSIX shells.

## Native tool-call smoke test

Before spending full calendar eval runs on a model, verify it can emit structured Hermes tool calls. Send a harmless one-step task with the same tool schema surface and require:

- session provenance reports `tool_call_count >= 1`;
- `finish_reason=tool_calls` and non-empty `message.tool_calls[]`;
- no fenced `python`/JSON/XML pseudo tool calls in assistant content.

If the model returns only text-shaped tool invocations, classify as `native_tool_call_failure` and do not attribute to the calendar skill.

**Metric retrieval**: use `~/.hermes/state.db` sessions table, not stdout. Extract session ID from stderr (`session_id: <hex_id>`). If row absent, retry after 1–2s (WAL commit lag). With `--ignore-user-config`, `tool_call_count=0` means true model failure, not missing fallback.

Reject/skip full eval when smoke test shows only: fenced code blocks, `<tool_call>`/XML pseudo calls, prose describing commands, or provenance `0 tool calls`.

A text-to-tool bridge must be opt-in and conservative: standalone block only, known tool allowlist, valid JSON parameters, no mixed prose, no execution of examples from tool output.

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

## Evaluating the evaluator, not just the skill

Split the score into separate layers:

- `artifact_success`: `.ics` exists, expected bytes/event counts/timestamp fingerprint, privacy-safe mode.
- `envelope_contract_success`: `schema_version`, `ok`, `command`, `verification.ok`, `agent_handoff.ready`, and `artifact_inspection_required=false` are correct. Field list is authoritative in `contracts.py` `_AGENT_CONTRACT_TEMPLATE`.
- `tool_minimality`: successful happy path should be `read SKILL.md` + one `build auto`; extra `stat`, `ls`, `grep`, `cat`, or `doctor` are model/eval-surface behavior unless the build failed.
- `final_answer_protocol_success`: final response is exactly the requested one-line handoff and stops.

The durable pattern is:

1. Keep the full diagnostic envelope in `envelope.json`, but expose a compact happy-path handoff surface for agents/evals.
2. Put already-normalized delivery fields in code (`MEDIA:...`, safe caption/summary, `artifact_inspection_required=false`, `verification_ok=true`).
3. Canonicalize values in the CLI/schema, not in prompts or evaluators.
4. Make the model copy a ready delivery field or one-liner rather than compose it from multiple envelope fields.

## Deterministic runtime flow for weak/non-tool models

Two different questions:

1. **Skill/runtime correctness** — does the code-owned CLI generate and verify a calendar artifact?
2. **Model-as-agent ability** — can a model choose and emit native Hermes `tool_calls` to run the workflow?

Do not flatten these into one pass/fail. A model can fail tool calling while the skill/runtime is healthy.

For weak or non-tool-call-native models, use a deterministic handler:

```text
user input -> private source file -> flight_calendar_ics.py --json build auto -> parse JSON handoff -> deliver MEDIA + safe_summary
```

The model should only receive the code-owned safe summary and may write a human-readable caption. It should not see private booking URLs/PNR/passenger/ticket/contact/payment values and should not be responsible for shell execution, artifact validation, or result JSON normalization.

For skill/runtime regression evaluation:

1. Copy private input with mode `0600`; compare only bytes/hash equality, never print the value.
2. Run the skill-owned CLI directly.
3. Parse stdout as compact JSON handoff.
4. Require: `ok=true`, `agent_handoff.ready=true`, `artifact_inspection_required=false`, `safe_summary.verification_ok=true`, `MEDIA:` handoff, expected segment/event counts, `.ics` mode `0600`, no placeholders, privacy scan clean.
5. Write per-run `result.json`, then aggregate by layer.

Report status by layer: `flight-calendar-ics CLI/runtime`, `model tool-calling`, `delivery/final response`.

## UX pitfall

Do not treat a terse user message such as `3.` as sufficient approval to write files or run a new evaluation unless the numbered choice is unambiguous and current. When in doubt, explain the interpretation first or ask a short clarification.

## Golden Path Principles

1. **INSTRUCTION MINIMALISM** — each step = ONE action.
2. **ATTENTION NARROWING** — list only what to EXTRACT, never what was VERIFIED.
3. **EXPLICIT TERMINATION** — "this completes the task" + "Then respond to the user".

## Why models make redundant verification steps (causal model)

Even with an explicit handoff contract (`artifact_inspection_required=false`, code-owned `safe_summary`), models run 1–3 extra terminal calls after a successful `build auto`. The irreducible minimum for the happy path is 4 steps (read prompt, read SKILL.md, terminal build, write result). Root causes form 5 layers:

1. **Training-data prior (~50%)**: LLMs trained on examples where "verify file exists" = `os.path.exists()`. Short prompt instructions cannot override trillions of training tokens.
2. **Prompt ambiguity (~25%)**: Action verbs ("проверь") trigger verification. Replace with extraction verbs + explicit envelope field mapping.
3. **Authority gap (~15%)**: Models rank direct observation > claims in data > prose instructions. Add explicit data claims like `no_further_action_needed: true`.
4. **Model-specific biases (~10%)**: gpt-oss:20b "prepare environment" pattern; gemma4:31b "insurance behavior" double verification.
5. **Insurance behavior**: Proportional to contract ambiguity. v1.6.0→v1.7.0 improvement (8→5, 10→5, 14→7) confirms explicit handoff reduces "insurance premiums."

### Concrete fixes ranked by impact

1. **Rewrite eval prompt**: Replace "проверь X, Y, Z" with "извлеки из data.agent_handoff.safe_summary: X, Y, Z. НЕ запускай terminal для проверки."
2. **SKILL.md hardening**: "На happy path НЕ запускай terminal-команды после build auto."
3. **Envelope field**: Add `no_further_action_needed: true` to top-level JSON.
4. **Remove gpt-oss sequential_thinking** from eval tool access.
5. **Combine prompt+SKILL.md reads** into one skill_view to reduce 4-step minimum to 3.

### Irreducible Floor

| Waste type | Cause | Fix |
|------------|-------|-----|
| Text-addressable | Verification fields, compound instructions | SKILL.md golden path |
| Training prior | Micro-checks (mkdir, ls, pwd) | Irreducible via text |
| Stochastic | seq_thinking, post-write terminal | Toolset restriction |

Production floor: 6 tools (4 core + 2 micro-checks). With `enabled_toolsets: ['terminal', 'file']`: potentially 4–5 tools.

### Trigger-Word Backfire (v1.7.4 evidence)

"CLI owns all verification" and "only terminal command" are trigger words that re-activate the verification prior regardless of context:
- gemma4: 5→9 (+4), gpt-oss: 7→8 (+1)
- Use transition instructions instead: "Then respond to the user"

## v1.7.0 cross-model evaluation (2026-06-14)

Branch: `feat/icalendar-vtimezone-migration`. Key change: `icalendar` library migration, VTIMEZONE+TZID format.

| Model | v1.6.0 tools | v1.7.0 tools | Δ |
|-------|:-----------:|:-----------:|:---:|
| gemma4:31b | 8 | 5 | −3 |
| gemini-3-flash | 8 | 5 | −3 |
| deepseek-v4-flash | 10 | 5 | −5 |
| gpt-oss:20b | 14 | 7 | −7 |

All 4: SUCCESS, `doctor_used=False`, `privacy_exposed=False`, `retries=0`.

Key findings: ICS format change (UTC-only → TZID+VTIMEZONE). Tool call efficiency uniformly improved. gpt-oss:20b transformation (200s→26s, 14→7 tools) is a handoff contract win. deepseek-v4-flash: −37% time, −50% tool calls.

## v1.7.7→v1.7.8 multi-run evaluation (2026-06-14, N=5)

Top-level `no_further_action_needed: true` promotion from `agent_handoff` to JSON root.

**deepseek_v4_flash** — signal works ✅: med 6→5, σ↓3.5×, tool_minimality 2/5→4/5.
**gemini_3_flash_preview** — neutral ≈: med 3→3, variance slightly increased.
**gemma4_31b** — not capable ❌: 0/10 artifact success, always 2 tools, never follows SKILL.md runbook.

**Conclusions**: top-level `no_further_action_needed` works for deepseek; neutral for gemini; irrelevant for gemma4. Fallback clean: 0/30 sessions with "Fallback activated". Zero tool calls: 0/30.

## Harness operational notes

- **Sessions DB**: authoritative metric source for `hermes chat -Q`. Extract session ID from stderr, query `~/.hermes/state.db`.
- **WAL commit lag**: use `sqlite3.connect(f"file:{db}?mode=ro", uri=True)` with 5 retries × 1s delay.
- **Python stdout buffering**: `subprocess.run(capture_output=True)` — monitor filesystem artifacts (`run_metrics.json`) for progress, not stdout.
- **Version switching**: harness toggles `no_further_action_needed` in `parser.py` via string replacement. Always restore v1.7.8 (top-level enabled) after eval.
- **gpt-oss:20b**: excluded from all multi-run evals (persistent empty-content failure, 0 native tool calls).