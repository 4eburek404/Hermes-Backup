# Plan: flights runtime HEAD refresh and verification

## Goal
Скачать актуальный `flight-search` skill и companion `flights` CLI из GitHub `4eburek404/Hermes` `main`, внедрить их в реальный локальный runtime Hermes и проверить production-shaped поиском для `SVX→BCN` на `2026-08-16`.

## Context
- Requested from Telegram on 2026-05-07 after previous investigation used a temp checkout and local skill that might be stale.
- Host time checked: `2026-05-07 15:35:33 CEST +0200`.
- GitHub `main` resolved in this run to commit `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
- Runtime paths verified:
  - skill: `/home/konstantin/.hermes/skills/productivity/flight-search`
  - CLI source: `[legacy CLI path removed; current source is the development repo skills tree]/flights`
  - executable shim: `/home/konstantin/.local/bin/flights`
  - Python module path after install: `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__init__.py`

## Non-goals
- Do not edit `SOUL.md`, `USER.md`, or `MEMORY.md`.
- Do not change unrelated Hermes core/provider/cron/gateway configuration.
- Do not restart/reset the gateway; report prompt-cache/runtime caveat explicitly.
- Do not delete unrelated local research/cache/credential files.
- Do not print secrets/tokens/credential values.

## Steps
- [x] Load relevant skills and read plan governance policy.
- [x] Inspect current runtime: skill path, CLI path/version/module path/package metadata, current source state.
- [x] Resolve latest GitHub `main` commit and sparse-clone relevant source trees.
- [x] Compare upstream vs runtime, including airport normalization code/tests and skill references.
- [x] Sync latest skill and CLI into runtime paths.
- [x] Reinstall editable package metadata and executable shim.
- [x] Verify runtime: `skill_view`, skill inventory/no duplicate legacy, `flights --version`, module path, `doctor`, tests.
- [x] Run production-shaped `SVX→BCN 2026-08-16` search from the runtime CLI and inspect FLI airport normalization.
- [x] Patch runtime bug: FLI ambiguous final airport names now use query destination/origin as preferred context when it is one of the catalog matches.
- [x] Add regression tests for `Barcelona International Airport` ambiguity (`BCN` vs `XJB`) and rerun tests.
- [x] Correct premature fact_store claims about `enum_code()` / `BAR-DUB-LON` being latest root cause.
- [x] Remove temporary sparse checkout and archive this plan after verification.

## Verification
- GitHub source:
  - `git ls-remote https://github.com/4eburek404/Hermes.git refs/heads/main` returned `cb2e1cedd4efdcf13538cc9364a649e2a59eb091`.
  - Sparse checkout `git rev-parse HEAD` matched the same commit.
- Runtime before fix:
  - `flights_cli.__file__` initially pointed to `/tmp/hermes-4eburek404-cli/skills/<category>/<skill>/cli/flights/flights_cli/__init__.py`, proving runtime was bound to a temp checkout.
- Runtime after reinstall:
  - `command -v flights` → `/home/konstantin/.local/bin/flights`.
  - `flights --version` → `flights 0.8.0`.
  - package metadata → `flights-cli 0.8.0`.
  - module path → `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__init__.py`.
  - `flights --json doctor` → `ok=True`, `version=0.8.0`, cache dir exists, catalog `stale_count=0`.
- Skill:
  - `skill_view('flight-search')` loaded `/home/konstantin/.hermes/skills/productivity/flight-search/SKILL.md`.
  - Skill source parity with GitHub HEAD: `missing=0`, `extra=0`, `different=0`.
  - Frontmatter scan: exactly one flight-related installed skill; `flight-search-routing` absent.
- Source parity / local patch:
  - Before local bugfix, skill and CLI source were parity with GitHub HEAD after sync.
  - After local bugfix, expected differences from GitHub HEAD are exactly:
    - `flights_cli/providers/fli_mcp.py`
    - `tests/test_fli_mcp.py`
  - Patch artifacts saved:
    - `/tmp/flights-runtime-verify-after-fix/fli_mcp_local_fix.diff`
    - `/tmp/flights-runtime-verify-after-fix/test_fli_mcp_local_fix.diff`
- Tests:
  - Before local bugfix after sync: `84 passed, 9 subtests passed`.
  - After local bugfix/regression tests: `86 passed, 9 subtests passed`.
- Raw/provider evidence:
  - FLI raw `IST→BCN` returned legs with `departure_airport='Istanbul Airport'`, `arrival_airport='Barcelona International Airport'`, e.g. `VY3071` 18:10→21:00.
  - Catalog key for `Barcelona International Airport` becomes `('barcelona',)` and matches both `BCN` (`Barcelona-El Prat Airport`) and `XJB` (`Barcelona Bus Station`), causing the GitHub HEAD ambiguity error.
- Runtime smoke after local fix:
  - `flights --json fli-search IST BCN --depart-date 2026-08-16 --direct-only --no-cache --limit 10` → `ok=True`, `offer_count=5`, destinations normalize to `BCN`.
  - `flights --json fli-search DXB BCN --depart-date 2026-08-16 --direct-only --no-cache --limit 10` → `ok=True`, `offer_count=3`, destinations normalize to `BCN`.
  - `flights --json fli-search CDG BCN --depart-date 2026-08-16 --direct-only --no-cache --limit 3` → `ok=True`, destinations normalize to `BCN`.
  - `flights --json route live-assemble SVX BCN --depart-date 2026-08-16 --profile business --agent-brief` → `ok=True`, `candidate_count=20`, `failure_count=0`, `ranked_output_count=10`.
- Route result after fix:
  - Best CLI-ranked option: `87 025 RUB`, risk `excellent/0`, elapsed `10h20`: `U6773 SVX 07:20→IST 10:50` + `TK1855 IST 15:00→BCN 17:40`.
  - Cheapest high-ranked segment-assembled option in top output: `52 735 RUB`, elapsed `13h40`: `U6773` + `VY3071`.
  - Aggregate control found cheaper provider-assembled route: `41 942 RUB`, `3F478 + 3F247 + VY6333`, but requires booking-screen verification for protection/baggage/fare rules.
- Cleanup:
  - Temporary sparse checkout `/tmp/hermes-4eburek404-head-zQILIN` removed; verification artifacts under `/tmp/flights-runtime-verify-after-fix/` retained.

## Risks / pitfalls
- Upstream semantic version remains `0.8.0`; commit hash and module path are the freshness proofs.
- Runtime now contains a local bugfix on top of GitHub HEAD in two files; if upstream updates later, this patch should be upstreamed or re-applied intentionally.
- Current Telegram/gateway prompt snapshot may still include stale skill text until `/reset`; live `skill_view` and the `flights` executable already see the updated runtime.
- FLI provider behavior is live/upstream-dependent; the durable root cause is in normalization/ambiguity handling, not proof of route absence.

## Status
Current status: done

## Notes
- 2026-05-07: Completed GitHub HEAD sync, fixed temp-checkout runtime binding, reverted premature local flight-search skill patches by syncing skill from HEAD, implemented and tested a targeted FLI ambiguity fix in runtime, corrected stale fact_store records, and verified `SVX→BCN` live assembly succeeds with no provider failures.
- 2026-05-07: Patched reusable Hermes snapshot-sync reference to avoid deleting a temp checkout while any tool/process cwd is inside it; this prevents `getcwd: No such file or directory` after cleanup.
