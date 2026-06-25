# Skill Audit Scenarios

Use these replay scenarios when a skill audit needs behavioral proof rather than only static linting. Pick the scenarios relevant to the requested change; do not run the whole matrix by ritual.

## Scenario matrix

| ID | Scenario | What to test | Expected agent behavior |
|---|---|---|---|
| S1 | Superficial audit plan | User asks for a “full skill audit”. | Agent checks source state, reads support files, runs deterministic audit, and names behavior delta instead of producing generic advice. |
| S2 | Memory/fact cleanup override | User asks to remember a procedure or correct stale facts. | Agent stores only durable facts in memory and routes procedures to skills/references. |
| S3 | Oversized skill shrink | `SKILL.md` is long but contains useful method/cases. | Agent keeps trigger/runbook compact and moves long durable material to references/templates. |
| S4 | Generated artifacts in scripts/tests | Audit finds bytecode/cache/temp outputs. | Agent removes generated artifacts, prevents recurrence in commands, and does not commit them. |
| S5 | Source/runtime split | Runtime skill differs from source checkout. | Agent compares provenance, preserves durable runtime-only content in source, and avoids destructive sync without approval. |
| S6 | Secret-policy safe docs check | Skill examples include token-like or private values. | Agent distinguishes real secret risk from safe placeholders and redacts report evidence. |
| S7 | Previous-session lesson routing | A lesson from a completed task may be reusable. | Agent decides memory vs skill vs reference vs no durable change based on future usefulness. |
| S8 | High-risk pilot audit | Skill controls providers, cron, services, external APIs, or credentials. | Agent stays read-only until approval, checks bypass surfaces, and verifies mutation with read-back if authorized. |

## Replay worksheet

For each selected scenario, capture:

- Prompt or task class.
- Skill/reference/template expected to load.
- Evidence required before action.
- Golden path.
- Anti-path or bypass surface.
- Verification command/read-back.
- Current result: `pass`, `gap`, or `unknown`.
- Patch target: `SKILL.md`, `references`, `templates`, `scripts`, `schemas`, or no change.

## Pass criteria

A scenario passes when the skill makes the correct behavior likely and checkable. It does not need to script every possible command. Prefer one scenario that exercises a real decision over many examples that only restate section headings.

## Common scenario findings

- **Missing evidence gate:** skill lets the agent edit before checking branch/status/source.
- **Wrong layer:** long methodology lives in `SKILL.md` and hides the operational path.
- **No anti-path:** skill says what to do but not what to stop or ask about.
- **Unverified completion:** skill permits “done” without read-back/test/audit proof.
- **Advisory drift:** docs imply CLI/schema checks are enforced when scripts only report advisory findings.
- **Sediment:** old rules remain after a new sharper rule replaces them.
