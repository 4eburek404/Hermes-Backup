# Plan: Plans Folder Cleanup and Governance

## Goal
Clean `/home/konstantin/docs/plans/` and establish a durable management standard for plans.

## Context
User explicitly requested: “очисти папку plans. Затем нужно оформить стандарт управления папкой plans и планами внутри. Ищи best practices, анализируй, предлагай”.

## Non-goals
- Do not change cron/config/skills unless needed for documentation consistency.
- Do not delete completed plans destructively; preserve audit trail unless clearly unsafe/trash.
- Do not modify unrelated docs outside the plans governance surface unless verification requires it.

## Steps
- [x] Inventory existing plan files, statuses, sizes, and risk signals.
- [x] Research lightweight planning/ADR/task-doc best practices and adapt them to Hermes agents.
- [x] Choose cleanup policy: active root, archive for done/superseded/cancelled, no destructive deletion by default.
- [x] Move historical plans into archive structure.
- [x] Rewrite `plans/README.md` as the governance standard.
- [x] Verify links/files, secret scan, and final inventory.

## Verification
- [x] Root `plans/` contains README plus only active/current plans.
- [x] Historical plans are preserved under archive.
- [x] README explains lifecycle, statuses, naming, required sections, update rules, archive rules, and anti-patterns.
- [x] No token-like secrets introduced.

## Risks / pitfalls
- Overengineering folder policy — mitigated by keeping only root/README + archive/<year>/<status>.
- Losing audit trail by deleting historical plans — avoided; files moved, not deleted.
- Creating recursive clutter by adding governance plans while cleaning plans — this plan is closed and archived with the rest.
- Mixing plan governance with general docs governance — README is limited to plan lifecycle and archive policy.

## Status
Current status: done

## Notes
Implemented `/home/konstantin/docs/plans/README.md` governance standard and `archive/README.md`. Root is intended to contain only active plans plus README; closed plans are archived under `archive/2026/<status>/`.
