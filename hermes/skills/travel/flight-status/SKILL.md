---
name: flight-status
description: Use when checking the current operational status of a flight or airport board, including delays, cancellations, current times, terminals, and other status fields exposed by Trip.com; not for fare search.
version: 0.2
author: Hermes Agent
license: MIT
metadata:
  hermes:
    category: travel
    tags: [travel, flights, status, airport, delays]
    related_skills: [flight-search]
    requires_toolsets: [terminal]
---

# Flight Status

Use Trip.com as the flight-status source for this skill.

For the current development scope, do not switch to an airline site, airport site,
or another flight tracker when Trip.com is unavailable or incomplete. Report the
Trip.com limitation instead. This keeps provider behavior explicit while the
Trip.com integration is being developed.

Use `"${HERMES_SKILLS_PYTHON:-python3}"` as the Python interpreter for bundled
commands. When `HERMES_SKILLS_PYTHON` is set, use that exact executable;
otherwise use `python3`.

## Goal

Answer operational flight-status questions from Trip.com using the bundled
`scripts/trip_board.py` CLI. Keep this separate from fare search.

Trip.com identifies VariFlight as the data provider. Treat the result as
third-party flight-status data, not as an official airline or airport statement.

## Workflow

1. **Fix the operation.**
   - Record the flight number and operating date for a specific-flight request.
   - Resolve relative dates such as "today" to an absolute `YYYY-MM-DD` date
     before calling the CLI.
   - Flight numbers repeat by date; never use an undated result as the requested
     operation.

2. **For a specific flight, use specific-flight lookup.**
   Resolve `<skill-root>` as the directory containing this `SKILL.md` and run:

   ```bash
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" --flight SU1401 --date 2026-09-25 --json
   ```

   Do not require the user to provide the route, airport, or direction. The CLI
   uses Trip.com's specific-flight page and returns the route with the operation.

   For several explicitly requested flight numbers, run the same specific-flight
   lookup separately for each flight and report the results together.

3. **For an airport board, use board lookup.**
   Airport-board mode requires an airport and direction:

   ```bash
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" SVO --direction arrivals --json
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" SVO --direction departures --json
   ```

   The normal board mode returns Trip.com's current date/time slice and up to
   the first 24 eligible rows.

4. **Preserve the time semantics returned by the CLI.**
   - `scheduled.departure` and `scheduled.arrival` are the source's planned
     schedule.
   - If the CLI returns `actual`, report those values as actual times. Current
     evidence supports this for completed `Arrived` operations from the
     specific-flight source.
   - If the CLI returns `current`, keep that neutral label. Do **not** rename it
     to `actual`, `estimated`, `revised`, or "rescheduled" unless the source
     establishes that meaning.
   - Keep the status text separately.

5. **Report the result without reinterpretation.**
   Give the source status first, then the scheduled and `actual` or `current`
   times returned by the CLI, followed by route/terminal fields that are present
   and the observation time. Omit unavailable fields.

## Examples

Specific completed flight:

```text
SU1401 — 2026-09-25 — Arrived
Scheduled: departure 13:10; arrival 13:50
Actual: departure 13:58; arrival 14:06
Route: SVX → SVO
Source: Trip.com; data provider: VariFlight
```

For a result containing neutral current times:

```text
status: Delayed until 22:50
scheduled: departure 18:50, arrival 19:30
current: departure 22:50, arrival 23:06
```

report:

```text
SU1437 — 2026-09-25 — Delayed until 22:50
Scheduled: departure 18:50; arrival 19:30
Current on Trip.com: departure 22:50; arrival 23:06
Source: Trip.com; data provider: VariFlight
```

Do not turn `current` values into actual or estimated times unless the source
establishes that meaning.

## Errors and limitations

The CLI uses named errors such as:

- `trip_antibot_challenge`
- `trip_parser_changed`
- `trip_network_error`
- `trip_http_error`
- `trip_operating_date_mismatch`
- `flight_not_found`
- `airport_and_direction_required`
- `missing_dependency`

These mean the requested result could not be established from the current
Trip.com integration. They are not evidence that the real-world flight does not
exist or that it is on time.

Do not hide these failures by silently using another provider.

## Check

Before answering:

- flight number and operating date match the requested specific operation;
- a specific-flight request used the specific-flight CLI mode rather than
  requiring the user to supply airport/direction;
- airport and direction are supplied when using board mode;
- `scheduled`, `actual`, and `current` retain the semantics returned by the
  CLI;
- Trip.com status wording is not strengthened by inference;
- unavailable fields are omitted rather than guessed;
- Trip.com / VariFlight is identified as the source.

## Stop

Stop before fare search, rebooking, check-in, purchase, compensation, or other
travel actions unless the user separately asks for them.
