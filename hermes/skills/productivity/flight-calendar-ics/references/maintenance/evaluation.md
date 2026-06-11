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
