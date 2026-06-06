# Dead-code and contract cleanup notes

Use this reference when the user asks to audit `flight-calendar-ics` for dead code, stale tests, retired shims, generated artifacts, or skill-library dirt.

## Read-only audit shape

1. Prove both layers before conclusions:
   - canonical source: `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-calendar-ics`
   - active runtime: `/home/konstantin/.hermes/skills/productivity/flight-calendar-ics`
   - check branch/status in the source repo and compare source/runtime manifests before any sync.
2. Prefer AST/static indexing before runtime poking:
   - enumerate Python defs/classes/imports/calls;
   - cross-check candidate unused symbols with full-tree text search;
   - classify dynamic CLI surfaces separately from truly unused helpers.
3. Verify that tests still cover active surfaces, not retired names:
   - detect tests that assert old compatibility names exist or fail closed;
   - replace long-lived “old name is empty/missing” tests with positive active-surface checks when retiring shims.
4. Run safe validation with bytecode disabled where possible:
   - `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/*.py tests/*.py`
   - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_flight_calendar_ics_cli -v`
   - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json doctor`
   - `PYTHONDONTWRITEBYTECODE=1 python3 scripts/travelpayouts_airport_catalog.py inspect`
5. Finish with generated-artifact hygiene:
   - no `__pycache__/` or `*.pyc` under runtime/source skill trees;
   - no temp `/tmp/flight-ics.*` artifacts left from diagnostics.

## Known cleanup surfaces

- Retired provider-helper timezone shims must not be preserved by long-lived absence tests. Keep only active catalog behavior checks: catalog loads, representative airports resolve, and explicit `--tz` overrides win.
- Direct helper commands/scripts (`make`, `aeroflot`, `ural`, `utair`, `redwings`) are compatibility/diagnostic surfaces while `references/core/cli-contract.md` and `doctor.data.legacy_scripts` still list them. Do not delete their tests piecemeal; first decide whether the public contract is being retired, then update parser routes, docs, doctor output, tests, and references in one contract patch.
- Compatibility helper tests that call Python `main()` directly can leak noisy stdout after `unittest OK`; capture stdout/stderr with `contextlib.redirect_stdout/redirect_stderr` or run a subprocess with capture when the output itself is not under test.
- Shared helper candidates are true cleanup only when behavior is identical across adapters. Keep carrier-shaped helpers local when names are similar but semantics differ, such as parser-specific `clean()` helpers.
- Runtime/source drift is a blocker for cleanup sync. Runtime-only durable references must be promoted to source or deliberately removed before source→runtime parity is claimed.
- Keep `references/registry.md` current. Every maintenance/core reference should have a semantic owner entry; missing registry entries cause duplicate future references.

## Reporting shape

Report findings as:

- **Confirmed dead code:** path, symbol, line range, evidence that no calls/references exist.
- **Legacy/compatibility surfaces:** path, docs/tests that still make them public, retirement dependency.
- **Tests covering stale names:** exact test name and whether to delete, rewrite, or keep as compatibility proof.
- **Generated artifacts:** exact paths and whether cleanup is safe.
- **Source/runtime parity:** manifest/hash differences and whether sync is safe.
- **Safe patch order:** smallest dead-code cleanup first, then contract/shim retirement, then registry/source-runtime sync.

Never print credential-bearing URLs, PNR keys, passenger/contact/payment data, or generated booking links while auditing.
