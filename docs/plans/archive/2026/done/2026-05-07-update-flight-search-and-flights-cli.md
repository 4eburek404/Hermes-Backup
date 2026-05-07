# Plan: update flight-search skill and flights CLI

## Goal
Install the refreshed flight-search skill and `flights` CLI from `https://github.com/4eburek404/Hermes/tree/main/cli` into Konstantin's local Hermes environment.

## Context
- Requested from Telegram on 2026-05-07.
- Host time checked: `2026-05-07 02:36:01 CEST +0200`.
- Source branch resolved: `4eburek404/Hermes` `main` at `3504460e76c164ee8ea85e6a325a5a7862b9a0a3`.
- Existing installed skill before the update: `productivity/flight-search-routing` version 2.4.3.
- Existing `flights` executable before the update: `/home/konstantin/.local/bin/flights`; source checkout: `/home/konstantin/code/clis/flights`.

## Non-goals
- Do not edit `SOUL.md`, `USER.md`, or `MEMORY.md`.
- Do not change unrelated Hermes core/provider/cron configuration.
- Do not restart/reset the gateway unless needed and explicitly reported.
- Do not delete the older `flight-search-routing` skill without a separate explicit cleanup decision.

## Steps
- [x] Inspect current local `flights` CLI installation and current skill files.
- [x] Clone/sparse-checkout the upstream `cli` directory from `4eburek404/Hermes` `main` into `/tmp/hermes-4eburek404-cli`.
- [x] Identify the refreshed skill file(s) and CLI package/entry point.
- [x] Install/sync the new skill into `/home/konstantin/.hermes/skills/productivity/flight-search`.
- [x] Sync the CLI source snapshot into `/home/konstantin/code/clis/flights` without deleting local research/cache/egg-info extras.
- [x] Refresh editable `flights-cli` package metadata and reinstall the `/home/konstantin/.local/bin/flights` shim.
- [x] Verify: skill loads, `flights` command resolves to the updated code, help/version/smoke command works, tests pass.
- [x] Promote compact durable facts to holographic `fact_store`.

## Verification
- `skill_view('flight-search')` succeeded and loaded `/home/konstantin/.hermes/skills/productivity/flight-search/SKILL.md`.
- Source parity check:
  - `flights-cli`: checked 52 source files; mismatches `0`.
  - `flight-search skill`: checked 3 source files; mismatches `0`.
- CLI checks:
  - `command -v flights` → `/home/konstantin/.local/bin/flights`.
  - `flights --version` → `flights 0.8.0`.
  - Python package metadata → `flights-cli 0.8.0`.
  - Module path → `/home/konstantin/code/clis/flights/flights_cli/__init__.py`.
  - `flights --json doctor` returned `ok: true`, cache files present, Travelpayouts env available.
  - `flights --catalog-refresh never --json route plan SVX LHR --depart-date 2026-07-19 --profile business` returned `ok: true`.
- Test suite: `python3 -m pytest -q /home/konstantin/code/clis/flights/tests` → `64 passed, 4 subtests passed in 4.88s`.

## Risks / pitfalls
- The older `flight-search-routing` skill remains installed. This avoids destructive cleanup without explicit delete approval, but future sessions may see both skills until the old one is retired or patched to point to the new workflow.
- Current Telegram session prompt was built before the new skill existed; a fresh session/reset is needed for it to appear in the always-on available skills list.
- CLI source was already content-identical to the GitHub `main` snapshot except local extras (`aeroflot_research`, `.pytest_cache`, `flights_cli.egg-info`); the actual update refreshed the skill installation and stale package metadata from 0.7.0 to 0.8.0.

## Status
Current status: done

## Notes
2026-05-07: Completed update from `4eburek404/Hermes` main commit `3504460e76c164ee8ea85e6a325a5a7862b9a0a3`. Installed new `flight-search` skill, refreshed editable `flights-cli` metadata and shim, verified smoke commands and tests. No `SOUL.md`/`USER.md`/`MEMORY.md`, cron, provider, or gateway config changes were made.
