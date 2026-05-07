# Plan: change flights same-airport default minimum to 120 min

## Goal
Change the default same-airport self-transfer/layover minimum in the local `flights` CLI and the `flight-search-routing` skill documentation from 180 min to 120 min, preserving cross-airport default at 300 min.

## Context
- User request: "default same airport сделайте 120 min".
- Relevant CLI source: `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__main__.py`.
- Relevant tests: `[legacy CLI path removed; current source is the development repo skills tree]/flights/tests/test_offline.py`.
- Relevant skill docs: `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md` and `references/layover_rules.md`.
- `[legacy CLI path removed; current source is the development repo skills tree]/flights` is not a git repository; do not make branch/commit/release claims.

## Non-goals
- Do not change cross-airport default (`300 min`).
- Do not add new live pricing/search features.
- Do not change provider/API semantics or cached price behavior.

## Steps
- [x] Inspect current code/tests/docs occurrences of same-airport minimum.
- [x] Add or update a test that expects the default same-airport route-plan minimum to be 120 min; verify it fails before code change.
- [x] Change the CLI default from 180 to 120 min.
- [x] Update skill docs/reference docs/checklists from 180 to 120 min.
- [x] Run targeted test, full test suite, and a JSON smoke route-plan check.

## Verification
- [x] Targeted test failed before code change and passed after code change.
- [x] Full CLI test suite passed: `29 passed, 4 subtests passed` via pytest.
- [x] `make test` passed: `Ran 29 tests ... OK`.
- [x] `route plan` smoke JSON showed same-airport required minimum `[120, 120]` for hubs `IST`, `DXB`.
- [x] Skill/reference docs contain 120 min same-airport default and no stale 180-min same-airport default claims were found in the skill directory.

## Risks / pitfalls
- Do not confuse same-airport default with cross-airport default.
- Do not document a value different from actual `argparse` default.
- Do not assume git/CI context without verified repository root.

## Status
Current status: done

## Notes
Completed 2026-05-04. Changed all CLI `--min-same-airport-min` route-command defaults to 120 while keeping cross-airport at 300. Added regression coverage for route command defaults and smoke-verified `route plan` JSON. Updated `flight-search-routing` skill docs and `references/layover_rules.md`. No branch/commit/release claims because `[legacy CLI path removed; current source is the development repo skills tree]/flights` is not a git repository.
