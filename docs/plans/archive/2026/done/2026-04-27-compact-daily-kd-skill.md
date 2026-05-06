# Plan: Compact daily-knowledge-distillation skill

## Goal

Сократить `daily-knowledge-distillation` skill без потери safety-critical правил: execution modes, no-edit semantics, source budget, batch/parallel extraction, candidate quality gate, agent mistake handling, post-write verification, audit report.

## Context

Skill вырос до ~23.3k chars / 527 lines после добавления batch/parallel rules. Для daily cron лучше держать runtime skill компактнее, а setup/model-benchmark детали вынести в `/home/konstantin/docs/runbooks.md`.

## Non-goals

- Не менять cron job.
- Не менять model pinning.
- Не редактировать built-in memory.
- Не удалять смысловые safety rules.

## Steps

- [x] Read current skill, skill authoring guidance, and runbooks.
- [x] Move setup/model-benchmark operational details to runbooks if missing.
- [x] Rewrite skill into compact runtime-focused version.
- [x] Verify skill loads, YAML is valid, and required markers remain.
- [x] Measure size reduction.
- [x] Mark this plan done.

## Verification

- `skill_view(name='daily-knowledge-distillation')` succeeds.
- Required markers exist: Execution Modes, Source Budget, Batch/Parallel, Quality Gate, Agent Mistake Handling, Post-write Verification.
- New skill size is materially smaller than 23.3k chars, target ~13–17k.
- Runbooks preserve setup/model-benchmark knowledge that was removed from the runtime skill.

## Risks / pitfalls

- Over-compressing could remove important guardrails.
- Moving details to runbooks should not make cron runtime dependent on long docs.
- Skill should remain self-contained enough for the cron to behave safely.

## Status

Current status: done

## Notes

Keep final user report compact.
