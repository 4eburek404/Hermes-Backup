# Evaluation & Golden Path Synthesis

**Date:** 2026-06-14
**Branch:** feat/icalendar-vtimezone-migration
**Models:** gemma4:31b, gemini-3-flash-preview, deepseek-v4-flash, gpt-oss:20b
**Ideal trajectory:** 4 tool calls (read SKILL → read source → terminal build → write result)

## v1.7.0 vs v1.6.0 Comparison

| Model | v1.6.0 | v1.7.0 | Δ |
|-------|:------:|:------:|:---:|
| gemma4:31b | 8 | 6 | −2 |
| gemini-3-flash | 8 | 5 | −3 |
| deepseek-v4-flash | 10 | 5 | −5 |
| gpt-oss:20b | 14 | 7 | −7 |

v1.7.0 improvements (VTIMEZONE+TZID, merged steps, safe_summary) reduced waste by 2–7 tools.

## SKILL.md Optimization: 9 Iterations

| Version | SKILL.md approach | gemma4 | gemini | deepseek | gpt-oss | Mean |
|---------|-------------------|:------:|:------:|:--------:|:-------:|:----:|
| v1.6.0v | verbose prompt + original | 8 | 8 | 10 | 14 | 10.0 |
| v1.7.0v | verbose prompt + merged | 6 | 5 | 5 | 7 | 5.8 |
| v1.7.0m | minimal prompt + merged | 11 | 5 | 10 | 4 | 7.5 |
| v1.7.1 | minimal + bare (no rails) | 8 | 10 | 7 | 6 | 7.8 |
| v1.7.2 | minimal + balanced guardrail | 5 | 7 | 8 | 6 | 6.5 |
| v1.7.3 | minimal + attention-control | 5 | 6 | 6 | 7 | 6.0 |
| v1.7.4 | + "CLI owns verification" | 9 | 6 | 6 | 8 | 7.2 |
| v1.7.5 | + transition instruction | 6 | 6 | 6 | 7 | 6.2 |
| v1.7.6 | + "from stdout" emphasis | 6 | 7 | 8 | 6 | 6.8 |

## Golden Path Principles

1. **INSTRUCTION MINIMALISM** — each step = ONE action.
2. **ATTENTION NARROWING** — list only what to EXTRACT, never what was VERIFIED.
3. **EXPLICIT TERMINATION** — "this completes the task" + "Then respond to the user".

## Trigger-Word Backfire (v1.7.4 evidence)

"CLI owns all verification" and "only terminal command" are trigger words
that re-activate the verification prior regardless of context:
- gemma4: 5→9 (+4), gpt-oss: 7→8 (+1)
- Use transition instructions instead: "Then respond to the user"

## Irreducible Floor

| Waste type | Cause | Fix |
|------------|-------|-----|
| Text-addressable | Verification fields, compound instructions | SKILL.md golden path |
| Training prior | Micro-checks (mkdir, ls, pwd) | Irreducible via text |
| Stochastic | seq_thinking, post-write terminal | Toolset restriction |

Production floor: 6 tools (4 core + 2 micro-checks).
With `enabled_toolsets: ['terminal', 'file']`: potentially 4–5 tools.

## Open Questions

- `no_further_action_needed: true` in CLI envelope (tool-level authority > SKILL.md)
- Multiple runs per version for statistical significance
- Temperature effects on stochastic waste