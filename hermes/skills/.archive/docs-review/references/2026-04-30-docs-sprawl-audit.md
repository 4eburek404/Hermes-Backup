# Docs sprawl audit snapshot — 2026-04-30

Session-derived reference for future `/home/konstantin/docs/` cleanup.

## Observed sizes

- `infrastructure.md`: 354 lines / ~15.4k chars. Mixed stable infrastructure map with detailed server-monitor/dashboard feature state.
- `runbooks.md`: 310 lines / ~12.9k chars. Mixed short procedures with benchmark policy, distillation policy, GitHub auth repair, Holographic hygiene, Himalaya details.
- `plans/README.md`: 206 lines / ~7.6k chars. Useful but heavy; can likely be compacted by merging repeated root/archive/lifecycle rules.
- `daily-knowledge-distillation` skill: ~365 lines / ~22.7k chars. Valuable but verbose for frequent loading.
- `docs-review` skill: ~317 lines / ~15.8k chars. Valuable but verbose.

## Active plans root issue

`/home/konstantin/docs/plans/2026-04-30-server-monitor-auth.md` was observed with completed status but still in the active root. It should be archived under `archive/2026/done/` if still completed.

## Cleanup order proposed

1. Re-run read-only inventory and secret scan.
2. Archive completed root plans.
3. Compact `runbooks.md` into short procedures/pointers.
4. Compact `infrastructure.md` into stable current system map/invariants.
5. Review `github-auth` for concise command/procedure only.
6. Review heavy skills: `daily-knowledge-distillation`, `docs-review`.

## Important user correction from the session

Do not turn a single incident into a long speculative “rail” or prohibition. For skills/runbooks, prefer the correct command/procedure and one concise pitfall over extended meta-policy.

## Current follow-up plan

Created:

`/home/konstantin/docs/plans/2026-04-30-docs-and-skills-cleanup.md`

Status at creation: `planned`.