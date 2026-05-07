# Plan: flights runtime HEAD refresh and verification

## Goal
Скачать актуальный `flight-search` skill и companion `flights` CLI из GitHub `4eburek404/Hermes` `main`, внедрить их в реальный локальный runtime Hermes и проверить production-shaped поиском для `SVX→BCN` на `2026-08-16`.

## Context
- Requested from Telegram on 2026-05-07 after previous investigation used a temp checkout and local skill that might be stale.
- Host time checked: `2026-05-07 15:35:33 CEST +0200`.
- Previous archived sync plan reported upstream commit `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`, but this run must resolve GitHub `main` again and verify runtime now.
- Relevant local runtime paths expected from durable facts / prior plans:
  - skill: `/home/konstantin/.hermes/skills/productivity/flight-search`
  - CLI source: `/home/konstantin/code/clis/flights`
  - executable shim: `/home/konstantin/.local/bin/flights`

## Non-goals
- Do not edit `SOUL.md`, `USER.md`, or `MEMORY.md`.
- Do not change unrelated Hermes core/provider/cron/gateway configuration.
- Do not restart/reset the gateway unless required; report prompt-cache/runtime caveat explicitly.
- Do not delete unrelated local research/cache/credential files.
- Do not print secrets/tokens/credential values.

## Steps
- [x] Load relevant skills and read plan governance policy.
- [ ] Inspect current runtime: skill path, CLI path/version/module path/package metadata, current git/source state.
- [ ] Resolve latest GitHub `main` commit and sparse-clone relevant source trees.
- [ ] Compare upstream vs runtime, including airport normalization code/tests and skill references.
- [ ] Sync latest skill and CLI into runtime paths if different or to reassert parity.
- [ ] Reinstall editable package metadata and executable shim.
- [ ] Verify runtime: `skill_view`, skill inventory/no duplicate legacy, `flights --version`, module path, `doctor`, tests.
- [ ] Run production-shaped `SVX→BCN 2026-08-16` search from the runtime CLI and inspect whether FLI airport normalization is correct.
- [ ] Correct premature skill/fact claims if GitHub/runtime evidence contradicts them.
- [ ] Update plan verification/status and archive when complete.

## Verification
- Exact upstream commit recorded from `git ls-remote` and sparse checkout `git rev-parse HEAD`.
- Runtime source parity checked for skill and CLI package trees.
- Package metadata and Python module path point to `/home/konstantin/code/clis/flights`, not `/tmp`.
- `flights --json doctor` succeeds.
- Relevant tests pass, or failures are recorded with exact scope.
- `SVX→BCN 2026-08-16` runtime smoke result is saved/inspected and reported with source boundaries.
- Any stale local skill/fact_store entries introduced during earlier investigation are corrected or clearly marked conditional.

## Risks / pitfalls
- Upstream semantic version may remain unchanged; commit hash is the real freshness proof.
- Current Telegram/gateway prompt snapshot may still include stale skill text until `/reset`, even if `skill_view` and runtime files are updated.
- `pip show flights` can refer to the unrelated Google Flights wrapper; the relevant package is `flights-cli`.
- FLI provider behavior may depend on live upstream/cache, so separate source-code normalization evidence from live-provider results.

## Status
Current status: in_progress

## Notes
- 2026-05-07: Plan opened because the user explicitly requested GitHub download, runtime implementation, and verification after a stale/local-copy concern.
