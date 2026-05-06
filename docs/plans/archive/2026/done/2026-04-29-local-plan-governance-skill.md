# Plan: Local Plan Governance Skill

## Goal
Create a user-local Hermes skill that acts as a thin procedural hook for Konstantin's plan governance, without duplicating the full canonical policy.

## Context
Konstantin confirmed the desired quality criteria:

- skill = thin procedural hook;
- README = full canonical policy;
- fact_store = retrieval pointer;
- built-in memory = always-on index;
- builtin `plan`/`writing-plans` = generic mechanics.

Canonical policy file: `/home/konstantin/docs/plans/README.md`.

## Non-goals
- Do not edit builtin `plan` or `writing-plans` skills.
- Do not copy the full governance README into the skill.
- Do not change Hermes config or cron jobs.

## Steps
- [x] Check existing skills and facts for duplicates.
- [x] Read the canonical plans README.
- [x] Create a local user skill as a thin routing/enforcement hook.
- [x] Validate the skill file/frontmatter.
- [x] Update holographic retrieval pointer if needed.
- [x] Close and archive this plan.

## Verification
- [x] Local skill exists under `~/.hermes/skills/`.
- [x] Skill content points to `/home/konstantin/docs/plans/README.md` as canonical source.
- [x] Skill does not duplicate the full README.
- [x] Skill explicitly preserves the layering model.
- [x] Plan is archived after completion.

## Risks / pitfalls
- Overly broad trigger could hijack project-local planning — mitigated by explicit project-local exception.
- Duplicating README would create future drift — mitigated by keeping the skill at ~5 KB and pointing to README.
- Current session may not auto-load the new skill until a new session/reset, depending on skill loader caching.

## Status
Current status: done

## Notes
Created local skill:

```text
/home/konstantin/.hermes/skills/note-taking/konstantin-plan-governance/SKILL.md
```

Validated frontmatter and size with Python:

```text
chars: 5106
description_chars: 231
```

Updated holographic `fact_id=33` to mention the local skill as the thin procedural hook while preserving `/home/konstantin/docs/plans/README.md` as canonical full policy.
