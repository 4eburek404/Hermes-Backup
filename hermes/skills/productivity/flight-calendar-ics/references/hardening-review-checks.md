# Flight calendar ICS hardening review checks

Session-derived checklist for future changes to the `flight-calendar-ics` skill. Use this when modifying the CLI, compatibility helpers, privacy handling, or tests.

## Why this exists

A blocker-only review found issues after the initial CLI contract work had already passed basic tests:

1. The new CLI wrote private `.ics` files as owner-only, but compatibility helpers could still write private artifacts with default umask-derived permissions.
2. `--json` command usage errors could bypass the machine-readable envelope because argparse parsing happened before the JSON-aware error handling path.
3. The test suite initially covered the preferred CLI path more thoroughly than legacy/direct helper paths.

## Durable review checklist

Before considering the skill clean:

- Run tests with `PYTHONDONTWRITEBYTECODE=1` and remove/check `__pycache__` / `*.pyc` afterward.
- Test both the preferred CLI and compatibility helpers:
  - `scripts/flight_calendar_ics.py --json make|validate|aeroflot|doctor`
  - `scripts/make_flight_ics.py` direct invocation
  - `scripts/aeroflot_pnr_to_itinerary.py` direct invocation, with network mocked/stubbed when testing permissions
- Under a permissive umask such as `022`, assert private artifacts are still mode `0600`:
  - generated `.ics`
  - Aeroflot-derived itinerary JSON
  - Aeroflot-derived `.ics`
- For `--json`, usage/argparse failures must still produce a valid JSON envelope:
  - non-zero exit, normally `2`
  - `ok=false`
  - `error.code=usage_error`
  - no raw argparse usage text in stderr for agent-facing JSON mode
- For validation failures with sensitive fixture values, assert stdout/stderr do not contain PNR, passenger names, ticket numbers, full booking URLs, or fixture sentinel strings.
- Re-run the skill audit helper and require no blocker/warning findings before commit.
- Run an independent blocker-only review after fixes, not only before fixes.

## TDD pattern for review findings

When a review finds a blocker:

1. Add a focused failing test reproducing the blocker.
2. Run only that focused test set and confirm RED.
3. Fix the smallest code path that owns the behavior.
4. Run focused tests, then the full relevant test suite, then smoke/audit.
5. Sync runtime changes into the source/backup repo only after the runtime skill is green and clean.

## Pitfalls

- Do not assume a new wrapper protects legacy helpers; direct helper invocation remains a public compatibility surface if documented or shipped.
- Do not rely on process umask for privacy-sensitive travel artifacts.
- Do not let `argparse.ArgumentParser.parse_args()` run outside the JSON-aware envelope path when `--json` is present.
- Do not treat a clean runtime skill as source-complete; verify the source/backup repo copy separately after sync.
