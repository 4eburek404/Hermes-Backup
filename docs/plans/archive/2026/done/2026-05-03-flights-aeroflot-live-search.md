# Plan: Aeroflot live search in flights CLI

## Goal
Add a truly live Aeroflot/Kupibilet-backed search path to `flights` so SVX → MOW on 2026-07-19 returns the full set of SU options instead of the Travelpayouts cached false-negative/partial result.

## Context
- Project path: `/home/konstantin/code/clis/flights`.
- Original execution note: implement directly with strict TDD; subagents are optional because the change is small and localized.
- Source design: add separate `kb-search` command using Kupibilet `frontend_search`, because earlier investigation found live-style results including the expected 11 SU options.
- Normalize offers into stable JSON and human output; support carrier and direct-only filters.
- Tech stack: Python stdlib `urllib.request`, existing argparse/unittest project style.
- Related follow-up plan: `/home/konstantin/docs/plans/2026-05-03-flights-remove-su-flights-legacy.md` tracks removal of legacy `su-flights` after the live workflow is available. Therefore this plan must not treat keeping `su-flights` as a durable final architecture decision.

## Non-goals
- Do not implement official `aeroflot.ru` scraping or booking.
- Do not claim Kupibilet results are official airline availability; verify purchase on the seller/airline before ticketing.
- Do not make broad CLI refactors unrelated to `kb-search`.
- Do not remove `su-flights` in this plan; that is tracked separately.

## Steps
- [x] Add offline tests for Kupibilet payload and parsing in `/home/konstantin/code/clis/flights/tests/test_offline.py`.
- [x] Implement `build_kupibilet_payload` and `parse_kupibilet_frontend_search` in `/home/konstantin/code/clis/flights/flights_cli/__main__.py`.
- [x] Add CLI command `kb-search` with `origin`, `destination`, `--depart-date`, `--currency`, `--only-carrier`, `--direct-only`, `--timeout`, and `--limit`.
- [x] Add human renderer and JSON envelope support for `kb-search`.
- [x] Run offline unit tests and syntax checks.
- [x] Live-verify SVX → MOW on 2026-07-19 with `--only-carrier SU --direct-only --limit 20`.
- [x] Update `flight-search-routing` skill/runbook references so future Aeroflot live searches use `kb-search` with explicit live-source caveat.

## Verification
- [x] `PYTHONPATH=/home/konstantin/code/clis/flights python3 -m unittest discover -s tests -v` passes.
- [x] `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py` passes from the flights CLI project.
- [x] `flights --json kb-search SVX MOW --depart-date 2026-07-19 --only-carrier SU --direct-only --limit 20` returns a valid JSON envelope.
- [x] Live result has `offer_count` equal to the observed live expectation for the route/date or records a dated source-side deviation.
- [x] Human output from `flights kb-search SVX MOW --depart-date 2026-07-19 --only-carrier SU --direct-only --limit 20` lists SU-operated direct options or explains source limitations.
- [x] `flight-search-routing` no longer treats cached Travelpayouts output as authoritative Aeroflot live availability.

## Risks / pitfalls
- Kupibilet is not the official Aeroflot booking source; results need purchase-side recheck.
- Frontend/API payload shape may change without notice; parser should fail with a clear source error, not a false “no flights”.
- Live results can legitimately differ from the earlier observed 11 options; verification must record the source/date rather than hard-code stale expectations.
- Network timeouts and anti-bot behavior can make live verification flaky; keep offline parsing tests separate from live smoke checks.

## Status
Current status: done


## Notes
2026-05-05: active-plan audit — verified complete and archived.
Evidence:
- Offline tests: `PYTHONPATH=/home/konstantin/code/clis/flights python3 -m unittest discover -s tests -v` → 30 tests passed.
- Syntax: `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py` → passed.
- Live JSON: `flights --json kb-search SVX MOW --depart-date 2026-07-19 --only-carrier SU --direct-only --limit 20 --timeout 90` → `ok=true`, `http_status=200`, `offer_count=11`, `unique_flight_count=11`.
- Human output lists 11 direct SU-marketed options for SVX→MOW on 2026-07-19 and labels source as Kupibilet live aggregate with recheck caveat.
- `flight-search-routing` documents `kb-search` and live/cache caveats; current skill has no `su-flights` mentions.

- 2026-05-05: normalized from implementation note into canonical active plan. The original task detail was preserved as checkboxes and verification criteria.
