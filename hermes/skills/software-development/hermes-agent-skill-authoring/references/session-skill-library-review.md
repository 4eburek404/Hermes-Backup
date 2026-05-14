# Post-session Skill Library Review

Use this reference when the user asks to review a completed conversation and update the skill library. It is the compact bridge inside `hermes-agent-skill-authoring`; for full audit, improvement, validation, stale-path/secret scan, and commit workflow, load `skill-audit-and-improvement`.

## Target shape

Prefer class-level skills with rich `SKILL.md` bodies plus compact support files under `references/`, `templates/`, or `scripts/`. Do not create one narrow skill per session, PR, bug string, or feature codename unless no existing umbrella can reasonably own the learning.

## Decision order

1. Patch a skill that was loaded/consulted in the session if it governs the learning.
2. Otherwise patch an existing umbrella skill found via `skills_list`/`skill_view`.
3. Add a support file under the umbrella when the detail is session-specific, evidence-heavy, or too long for `SKILL.md`; then add a one-line pointer in `SKILL.md`.
4. Create a new class-level umbrella only when no existing skill covers the task class.

## What counts as a skill signal

- User corrected style, tone, format, legibility, verbosity, reporting order, or workflow.
- User expressed frustration about a repeated behavior.
- A non-trivial technique, workaround, validation sequence, tool usage pattern, or debugging path emerged.
- A loaded skill was missing a step, wrong, stale, or too narrow.
- The session changed source/runtime conventions, verification gates, security posture, or durable operational layout.

## How to encode learnings

- Behavioral corrections belong in the governing `SKILL.md` body, usually as a pitfall or explicit step, not only in memory.
- Session-specific evidence belongs in `references/<topic>.md`; keep it concise and reusable.
- Deterministic probes or validators belong in `scripts/`.
- Boilerplate to copy/modify belongs in `templates/`.
- If two skills overlap, report the overlap in the final answer so a curator can consolidate later.

## Verification

- Re-read the patched skill or ensure the patch target was exact.
- Make the final report list changed skill files and the reason.
- If no update was made, say `Nothing to save.` only when there was genuinely no correction, technique, or reusable workflow.
