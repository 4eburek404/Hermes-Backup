# Plan: Add batch and parallel extraction strategy to daily knowledge distillation skill

## Goal

Add a concise but enforceable batch + parallel extraction strategy to `daily-knowledge-distillation`, then analyze how to shorten/optimize the skill.

## Context

Konstantin asked to add the batch/parallel approach and then re-analyze the skill for reduction/optimization. Previous real-data tests showed long prompts can cause timeouts, especially for `glm-5.1:cloud`.

Target skill:

- `/home/konstantin/.hermes/skills/note-taking/daily-knowledge-distillation/SKILL.md`

## Non-goals

- Do not change cron toolsets/model pinning yet.
- Do not implement a script pipeline yet.
- Do not remove important safety rules while optimizing.

## Steps

- [x] Read current skill and plan rules.
- [x] Add a `Batch and Parallel Extraction Strategy` section.
- [x] Update checklist/pitfalls if needed.
- [x] Verify skill loads and required markers exist.
- [x] Analyze skill length and propose concrete optimization cuts.
- [x] Mark this plan done.

## Verification

- Skill loads with `skill_view`.
- Skill contains rules: batch trigger, candidate-only workers, parallel extraction allowed only for read/extract, serial merge/write, no per-batch patches.
- Final response includes concise optimization analysis.

## Risks / pitfalls

- Making the skill longer while trying to optimize it.
- Allowing parallel workers to write docs or mutate state.
- Overcomplicating cron before observing a real run.

## Status

Current status: done

## Notes

Keep additions operational and compact.
