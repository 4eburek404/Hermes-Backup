# Plan: Built-in Memory and SOUL Revision

## Goal
Audit and conservatively revise Hermes built-in `MEMORY.md`, `USER.md`, and `SOUL.md` so they stay compact, high-signal, and aligned with the current docs/skills/holographic memory architecture.

## Context
User asked: “пока работа идет, наведи ревизию в memory.md, user.md, soul.md”.

Relevant files:
- `/home/konstantin/.hermes/memories/MEMORY.md`
- `/home/konstantin/.hermes/memories/USER.md`
- `/home/konstantin/.hermes/SOUL.md`

Relevant source-of-truth layers:
- `/home/konstantin/docs/README.md`
- `/home/konstantin/docs/user-context.md`
- `/home/konstantin/docs/infrastructure.md`
- `/home/konstantin/docs/runbooks.md`
- `/home/konstantin/docs/plans/README.md`
- local skills: `docs-review`, `holographic-memory-hygiene`, `konstantin-plan-governance`
- holographic `fact_store`

## Non-goals
- Do not dump docs into built-in memory.
- Do not store task progress, raw logs, or secrets.
- Do not change cron/config/credentials unless a concrete stale claim in memory requires removal or pointer adjustment.
- Do not rewrite SOUL into a bloated policy document; keep it behavioural and compact.

## Steps
- [x] Inventory current `MEMORY.md`, `USER.md`, `SOUL.md` sizes and content.
- [x] Compare with docs and holographic facts for duplication/staleness.
- [x] Draft conservative replacements or targeted patches.
- [x] Back up current files.
- [x] Apply edits.
- [x] Verify sizes, secret scan, and key hooks.
- [x] Close and archive this plan.

## Verification
- [x] `USER.md` remains compact and focused on user identity/preferences.
- [x] `MEMORY.md` remains compact and focused on critical environment/process pointers.
- [x] `SOUL.md` keeps the agent behavioural protocol without duplicating docs/skills fully.
- [x] No secrets introduced.
- [x] Holographic feedback applied for facts used.
- [x] Plan moved to `archive/2026/done/` when complete.

## Risks / pitfalls
- Over-pruning may remove important always-on guardrails — mitigated by preserving all high-priority hooks.
- Over-expanding built-in memory defeats the curated-memory preference — mitigated by keeping `MEMORY.md` near 2.0k chars and `USER.md` near 1.1k chars.
- SOUL edits can alter agent behaviour too broadly — mitigated by clarifying existing principles and layer boundaries, not adding task-specific policy dumps.

## Status
Current status: done

## Notes
Mode: approved maintenance — user directly requested revision of these memory/SOUL files.

Backup:

```text
/home/konstantin/.hermes/backups/memory-revision-20260429-123231/
```

Final sizes:

```text
MEMORY.md: 2014 chars / 2729 bytes
USER.md:   1109 chars / 1868 bytes
SOUL.md:   2855 chars / 4459 bytes
```

Key changes:

- Removed exact credential paths from always-on `MEMORY.md` and redacted the same line in the backup.
- Added `konstantin-plan-governance` and `plans/README.md` split to built-in memory and SOUL.
- Added Gmail personal-only constraint to `USER.md`.
- Updated `SOUL.md` with explicit knowledge-layer boundaries.
- Updated holographic fact `fact_id=18` for current SOUL shape and `fact_id=8` to avoid keeping exact credential paths in always-on memory/docs.

Verification:

- Active memory files secret scan: 0 hits.
- Backup secret/path scan for targeted patterns: 0 hits after redaction.
- `fact_store contradict`: 0 results before edits.
