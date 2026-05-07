# Plan: refresh flight-search skill and flights CLI from GitHub

## Goal
Update Konstantin's local Hermes flight-search skill and companion `flights` CLI from the current `main` snapshot of `https://github.com/4eburek404/Hermes`, then verify runtime, skill inventory, and tests.

## Context
- User requested from Telegram on 2026-05-07 after switching model to OpenAI Codex gpt-5.5.
- Host time checked: `2026-05-07 13:35:51 CEST +0200`.
- Current installed CLI before refresh: `/home/konstantin/.local/bin/flights`, `flights 0.8.0`, editable package `flights-cli 0.8.0` from `[legacy CLI path removed; current source is the development repo skills tree]/flights`.
- Current installed skill before refresh: `/home/konstantin/.hermes/skills/productivity/flight-search`.
- Previous completed syncs on 2026-05-07 used upstream commits `3504460e76c164ee8ea85e6a325a5a7862b9a0a3` and later `9551041ed4fde3833a130a21134aeebdd4c9f25d`; this run resolved the current upstream commit again.

## Non-goals
- Do not edit `SOUL.md`, `USER.md`, or `MEMORY.md`.
- Do not change unrelated Hermes core/provider/cron/gateway configuration.
- Do not delete unrelated local research/cache directories.
- Do not restart/reset the gateway; only report prompt-cache caveat.

## Steps
- [x] Load relevant Hermes/flight-search/plan skills and read the plan governance policy.
- [x] Inspect current local `flights` CLI, package metadata, doctor output, and current skill.
- [x] Resolve exact upstream `main` commit for `4eburek404/Hermes`: `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
- [x] Sparse-clone only the relevant source trees into `/tmp/hermes-4eburek404-cli-iPzKX1` and identify source layout: `cli/skills/flight-search` is now a symlink to `hermes/skills/productivity/flight-search`.
- [x] Sync `hermes/skills/productivity/flight-search/` into `/home/konstantin/.hermes/skills/productivity/flight-search/` with exact parity.
- [x] Sync `skills/<category>/<skill>/cli/flights/` controlled source directories into `[legacy CLI path removed; current source is the development repo skills tree]/flights/` with exact parity for `flights_cli/`, `tests/`, `docs/`, `Makefile`, `README.md`, and `pyproject.toml`.
- [x] Reinstall editable package metadata and refresh `/home/konstantin/.local/bin/flights` shim.
- [x] Verify source parity, skill inventory/no duplicates, CLI version/module path/package metadata, `doctor`, route-plan smoke command, help flags, and tests.
- [x] Update compact durable fact_store records for the new commit/current workflow.
- [x] Remove temporary checkout and archive this plan after verification.

## Verification
- GitHub source:
  - `git ls-remote https://github.com/4eburek404/Hermes.git refs/heads/main` returned `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
  - Sparse checkout `git rev-parse HEAD` matched `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
- Skill:
  - `skill_view('flight-search')` loaded `/home/konstantin/.hermes/skills/productivity/flight-search/SKILL.md`.
  - Linked files now: `references/debug-playbook.md`, `references/report-contract.md`, `references/source-boundaries.md`.
  - `skills_list(category='productivity')` shows `flight-search`.
  - Frontmatter scan found exactly one flight-related installed skill and `flight-search-routing` absent.
- Source parity:
  - `skill`: `src_files=5`, `dst_files=5`, `missing=0`, `extra=0`, `different=0`.
  - `flights_cli`: `src_files=41`, `dst_files=41`, `missing=0`, `extra=0`, `different=0`.
  - `tests`: `src_files=12`, `dst_files=12`, `missing=0`, `extra=0`, `different=0`.
  - `docs`: `src_files=1`, `dst_files=1`, `missing=0`, `extra=0`, `different=0`.
  - Top-level `Makefile`, `README.md`, `pyproject.toml`: equal to upstream.
- Runtime:
  - `command -v flights` → `/home/konstantin/.local/bin/flights`.
  - `flights --version` → `flights 0.8.0`.
  - Python package metadata: `flights-cli 0.8.0`.
  - Python module version: `0.8.0`.
  - Python module path: `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__init__.py`.
  - `flights --json doctor`: `ok=True`, command `doctor`, version `0.8.0`, Travelpayouts token available, catalog `stale_count=0`.
  - `flights --catalog-refresh never --json route plan SVX LHR --depart-date 2026-07-19 --profile business`: `ok=True`, command `route plan`, strategy `ru-priority`, `segments=7`.
  - `flights route --help` contains `live-assemble` and `kb-assemble`.
  - `flights route live-assemble --help` contains `--agent-brief` and `--aggregate-control-carrier`.
- Tests:
  - `python3 -m pytest -q [legacy CLI path removed; current source is the development repo skills tree]/flights/tests` → `84 passed, 9 subtests passed in 7.83s`.
- Cleanup:
  - Temporary sparse checkout `/tmp/hermes-4eburek404-cli-iPzKX1` removed and verified absent.

## Risks / pitfalls
- Upstream semantic version remains `0.8.0`; the actual source update is identified by commit `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
- Current Telegram/gateway session prompt may still carry the previous available-skills snapshot until a fresh `/reset`; live `skill_view` already sees the updated skill.
- `pip show flights` is an unrelated Google Flights wrapper; the relevant package is `flights-cli`.

## Status
Current status: done

## Notes
- 2026-05-07: Completed fresh sync from `4eburek404/Hermes` main commit `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`. The skill was substantially simplified around CLI-first `route live-assemble --agent-brief` and `data.agent_report`; old `process-notes.md` was replaced by three focused references. CLI source gained agent-report contract/service files and tests. No `SOUL.md`, `USER.md`, `MEMORY.md`, cron, provider, or gateway config changes were made.
