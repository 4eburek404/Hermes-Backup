# Plan: Improve daily-knowledge-distillation skill

## Goal

Patch the user-local `daily-knowledge-distillation` skill with the six requested P0/P1 improvements:

1. Execution modes.
2. Strict "do not edit files" scope.
3. Source budget.
4. Candidate quality gate.
5. Agent mistake handling.
6. Post-write verification.

## Context

Konstantin asked to implement the six P0/P1 improvements after a real-data benchmark exposed practical weaknesses:

- large source packets can cause model timeouts;
- dry-run/benchmark mode needs stricter no-write boundaries;
- agent mistakes should be abstracted into durable operational rules, not logged as incidents;
- distillation needs pre-write and post-write gates.

Relevant files:

- Skill: `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`
- Docs rules: `/home/konstantin/docs/README.md`
- Plans rules: `/home/konstantin/docs/plans/README.md`

## Non-goals

- Do not change cron schedule/model pinning.
- Do not rewrite the entire skill unless a targeted patch is insufficient.
- Do not add raw benchmark outputs to long-term docs.
- Do not create a new skill.

## Steps

- [x] Read current skill and relevant docs/plan rules.
- [x] Create this plan before editing the skill.
- [x] Patch the skill with the six requested improvements.
- [x] Verify the skill loads via `skill_view`.
- [x] Inspect the changed sections for duplicates, over-bloat, and consistency.
- [x] Mark this plan done and report the exact changes.

## Verification

- `skill_view(name="daily-knowledge-distillation")` succeeds after patching.
- The skill contains sections/rules for all six requested improvements.
- The final content remains under Hermes skill size limits.
- No secrets, raw logs, or benchmark transcripts are added.

## Risks / pitfalls

- Making the skill too long or philosophical instead of operational.
- Duplicating existing rules in multiple sections.
- Over-constraining normal cron mode so much that useful updates are skipped.
- Forgetting that benchmark/dry-run no-write boundaries must include `plans/`, skills, config, memory, cron, and target docs.

## Status

Current status: done

## Notes

Patch should be targeted and operational: modes, budgets, gates, mistake handling, and verification.
