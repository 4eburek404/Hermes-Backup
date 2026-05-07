# Plan: Remove legacy `su-flights` command

## Goal
Remove the legacy Travelpayouts `flights su-flights` command so Aeroflot searches have one clear live workflow: `flights kb-search ... --only-carrier SU`.

## Context
- Project path: `[legacy CLI path removed; current source is the development repo skills tree]/flights`.
- Original execution note: execute directly with strict TDD; this local project is documented as not being a git repository, so branch/commit steps are not available there.
- Architecture: delete the public parser entry, command handler, and human renderer for `su-flights`.
- Keep generic Travelpayouts request tooling (`flights request search`) intact because other workflows still use it.
- Related/precondition plan: `/home/konstantin/docs/plans/2026-05-03-flights-aeroflot-live-search.md` should provide and verify `kb-search` before legacy removal is treated as complete.

## Non-goals
- Do not remove generic Travelpayouts request/search tooling.
- Do not delete historical mentions of `su-flights` from archived plans unless they create current-source confusion.
- Do not change provider architecture beyond removing the legacy command surface.
- Do not claim Aeroflot availability without a live source caveat and purchase-side verification.

## Steps
- [x] Add regression test `test_su_flights_legacy_command_is_removed` using `build_parser().parse_args([...])` inside `assertRaises(SystemExit)`.
- [x] Run the targeted test and confirm RED while `su-flights` still parses.
- [x] Remove `command_su_flights` from `[legacy CLI path removed; current source is the development repo skills tree]/flights/flights_cli/__main__.py`.
- [x] Remove the `render_human` branch for `command == "su-flights"`.
- [x] Remove the `sub.add_parser("su-flights", ...)` block.
- [x] Update `flight-search-routing` skill and linked references so they document only the live `kb-search` Aeroflot workflow.
- [x] Run the full offline test suite and CLI smoke checks.

## Verification
- [x] `PYTHONPATH=[legacy CLI path removed; current source is the development repo skills tree]/flights python3 -m unittest discover -s tests -v` passes.
- [x] `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py` passes from the flights CLI project.
- [x] `flights --help` lists `kb-search` and does not list `su-flights`.
- [x] `flights kb-search --help` works.
- [x] `flights su-flights --help` exits non-zero with argparse `invalid choice`.
- [x] `flight-search-routing` has no current runnable workflow recommending `su-flights`.

## Risks / pitfalls
- Removing `su-flights` before `kb-search` is verified would leave Aeroflot searches without a clear CLI path.
- Generic Travelpayouts tooling must remain available for non-Aeroflot and diagnostic workflows.
- Documentation can drift if skill references still mention `su-flights` as current after code removal.

## Status
Current status: done


## Notes
2026-05-05: active-plan audit — verified complete and archived.
Evidence:
- Regression test `test_su_flights_legacy_command_is_removed` exists and passes in the full offline suite.
- Code indicators: no `command_su_flights`, no `add_parser("su-flights")`, no `render_human` branch for `su-flights`.
- `flights --help` lists `kb-search` and does not list `su-flights`.
- `flights kb-search --help` works.
- `flights su-flights --help` exits non-zero with argparse `invalid choice`.
- `flight-search-routing` has no current `su-flights` workflow.

- 2026-05-05: normalized from implementation note into canonical active plan. The removal remains planned and depends on the live `kb-search` workflow being available.
