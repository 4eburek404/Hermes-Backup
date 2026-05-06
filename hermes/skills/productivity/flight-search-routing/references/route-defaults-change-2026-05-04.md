# Route defaults change: same-airport minimum 120 min (2026-05-04)

## Trigger

User requested: `default same airport сделайте 120 min`.

## Scope

Changed the default same-airport separate-ticket minimum for local `flights` route commands from 180 to 120 minutes. Cross-airport default remained 300 minutes. Same-airport single-ticket rule remained 60 minutes inside `connection_rule(...)`.

## Files changed in that pass

- `/home/konstantin/code/clis/flights/flights_cli/__main__.py`
  - `add_common_route_flags(...)`: `--min-same-airport-min` default 120.
  - `route validate`: `--min-same-airport-min` default 120.
  - `route rank`: `--min-same-airport-min` default 120.
  - `route assemble`: `--min-same-airport-min` default 120.
- `/home/konstantin/code/clis/flights/tests/test_offline.py`
  - Added/updated regression coverage for route command defaults and route-plan exposed `required_min`.
- `SKILL.md`
  - Route Plan Contract and Verification Checklist updated to 120/300 defaults.
- `references/layover_rules.md`
  - Default flags, same-airport default, and application guidance updated to 120/300.

## Verification used

RED test before code change:

```text
AssertionError: 180 != 120
```

After code/doc updates:

```bash
python -m pytest -q /home/konstantin/code/clis/flights/tests
make test
/home/konstantin/.local/bin/flights --json route plan SVX LON --depart-date 2026-07-20 --hub IST --hub DXB
```

Observed result summary:

```text
29 passed, 4 subtests passed
Ran 29 tests ... OK
required_min=[120, 120]
cache_age_minutes_present=False
```

## Maintenance lesson

When changing a route default, do not patch just one argparse call. Check every route command that owns the same option (`plan`, `validate`, `rank`, `assemble`), update CLI docs and skill references, add/adjust tests for defaults, and smoke-check the JSON envelope that exposes the rule.

## Git caveat

`/home/konstantin/code/clis/flights` was not a git repository during this pass (`fatal: not a git repository...`), so no branch/commit/release claims were made.

## Supersession note: recommendation policy update 2026-05-05

This file records the 2026-05-04 CLI default change to 120 minutes. Current `flight-search-routing` recommendation policy is now: **90 min same-airport minimum acceptable**, **120 min same-airport business-preferred**. When the CLI default remains 120 but tight frontier candidates matter, pass `--min-same-airport-min 90` and label 90–119 min as tight.
