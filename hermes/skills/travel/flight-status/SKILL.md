---
name: flight-status
description: Use when checking the current operational status of a flight or airport board, including delays, cancellations, current times, terminals, and other status fields exposed by Trip.com; not for fare search.
version: 0.3
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

   The normal board mode returns all rows exposed by Trip.com for the board's
   current date. Do not truncate the source data to Trip.com's visible UI slice.

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

5. **Report Previous Flight when the CLI returns it.**
   - Treat `previous_flight` as Trip.com's Previous Flight relationship, not as
     proof that the same physical aircraft will operate both flights.
   - Report the Previous Flight number, route, status, and
     `scheduled`/`current`/`actual` fields that are present.
   - Use the normalized `previous_flight` returned by the CLI. Do not parse
     Trip.com HTML or independently reconstruct the child-flight lookup.
   - Do not calculate a missing ETA from delay text or scheduled times.
   - Do not turn the relationship into a turnaround verdict such as "the aircraft
     will make it" or "will not make it" unless the user separately asks for an
     assessment and the available evidence supports it.

6. **Report the result without reinterpretation.**
   Give the source status first, then the scheduled and `actual` or `current`
   times returned by the CLI, followed by route/terminal fields that are present
   and the observation time. If `previous_flight` is present, report it after
   the main operation. Omit unavailable fields.

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

In particular, `trip_operating_date_mismatch` means that the requested
operation could not be matched to that operating date in the Trip.com response
available to the CLI. It does not establish that the flight did not operate or
that the user's date is wrong. Trip.com may expose an incomplete set of
operations.

Do not hide these failures by silently using another provider.

## Check

Before answering:

- flight number and operating date match the requested specific operation;
- a specific-flight request used the specific-flight CLI mode rather than
  requiring the user to supply airport/direction;
- airport and direction are supplied when using board mode;
- `scheduled`, `actual`, and `current` retain the semantics returned by the
  CLI;
- when `previous_flight` is present, it is reported as Trip.com's Previous
  Flight relationship without asserting physical-aircraft identity;
- Previous Flight status/times come from the normalized CLI result rather than
  agent-side HTML parsing or reconstruction;
- `trip_operating_date_mismatch` is not interpreted as proof that the flight
  did not operate or that the requested date is wrong;
- Trip.com status wording is not strengthened by inference;
- unavailable fields are omitted rather than guessed;
- Trip.com / VariFlight is identified as the source.

## Stop

Stop before fare search, rebooking, check-in, purchase, compensation, or other
travel actions unless the user separately asks for them.
