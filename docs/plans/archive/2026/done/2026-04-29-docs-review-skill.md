# Plan: Docs Review Skill

## Goal
Create a reusable Hermes skill for reviewing `/home/konstantin/docs/` as an operational knowledge base: audit structure, freshness, duplication with holographic memory/skills, source-of-truth boundaries, stale plans, secrets risk, and proposed conservative edits.

## Context
The current memory architecture uses multiple layers:

- built-in memory as a compact index and critical rules;
- holographic memory for atomic durable facts and cross-domain retrieval;
- `/home/konstantin/docs/` for operational documentation, runbooks, infrastructure map, user context, and plans;
- skills for repeatable procedures;
- `session_search` for detailed history.

Konstantin asked for a dedicated `docs review` skill after analyzing whether docs should remain or be migrated to holographic memory.

## Non-goals
- Do not rewrite docs now.
- Do not migrate docs to holographic memory now.
- Do not mutate `fact_store` except if a short canonical pointer becomes clearly necessary after skill creation and duplicate search.

## Steps
- [x] Load relevant authoring and memory hygiene skills.
- [x] Inspect existing note-taking skills to avoid duplication.
- [x] Create user-local skill `docs-review` in category `note-taking`.
- [x] Validate frontmatter and structure.
- [x] Verify the skill can be loaded.
- [x] Report path, purpose, and trigger conditions.

## Verification
- `skill_manage(action=create)` returns success: done.
- `skill_view(name="docs-review")` loads the skill: done.
- Frontmatter has `name`, `description`, version, author, license, tags, related skills: done.
- Description is under 1024 chars: 287 chars.
- Skill distinguishes read-only review from mutation mode: done.
- Validated file: `/home/konstantin/.hermes/skills/note-taking/docs-review/SKILL.md`, 13,984 chars, 306 lines.

## Risks / pitfalls
- Duplicating `daily-knowledge-distillation`: avoid by making this skill audit/review first, not daily session distillation.
- Duplicating `holographic-memory-hygiene`: include cross-layer checks but do not turn docs review into fact_store cleanup.
- Over-editing docs: default mode must be read-only audit with proposed changes.

## Status
Current status: done

## Notes
Skill created and validated. It should be loaded for future requests like “проверь docs”, “сделай docs review”, “почисти docs”, “разбери, что должно быть в docs vs holographic vs skills”.
