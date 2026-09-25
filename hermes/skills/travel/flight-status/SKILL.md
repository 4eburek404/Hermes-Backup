---
name: flight-status
description: Use when checking the current operational status of a flight or airport board, including delays, cancellations, current times, terminals, and other status fields exposed by Trip.com; not for fare search.
version: 0.1
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

Answer operational flight-status questions from the Trip.com airport board using
the bundled `scripts/trip_board.py` CLI. Keep this separate from fare search.

Trip.com identifies VariFlight as the data provider. Treat the result as
third-party flight-status data, not as an official airline or airport statement.

## Workflow

1. **Fix the operation.**
   - Record the flight number and operating date.
   - Resolve relative dates such as "today" to an absolute `YYYY-MM-DD` date
     before calling the CLI.
   - Flight numbers repeat by date; never use an undated row as the requested
     operation.

2. **Choose the Trip.com airport board.**
   - If the origin airport is known, use its `departures` board.
   - If only the destination airport is known, use its `arrivals` board.
   - Do not invent an airport or route.
   - If the user gives only a flight number/date and no airport is available
     from the request or established context, the current CLI cannot discover
     the route from the flight number alone. State that limitation rather than
     switching providers or guessing.

3. **For one exact flight, use exact-flight lookup.**
   Resolve `<skill-root>` as the directory containing this `SKILL.md` and run:

   ```bash
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" SVX --direction departures --flight SU1437 --date 2026-09-25 --json
   ```

   Use the requested airport, direction, flight number, and date. Exact-flight
   lookup searches the matching source rows directly; it is not limited to the
   first 24 rows used by the normal board view.

4. **For an airport board, use board lookup.**

   ```bash
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" SVO --direction arrivals --json
   "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/trip_board.py" SVO --direction departures --json
   ```

   The normal board mode returns Trip.com's current date/time slice and up to
   the first 24 eligible rows.

5. **Preserve Trip.com's time semantics.**
   - `scheduled.departure` and `scheduled.arrival` are the source's planned
     schedule.
   - `current.departure` and `current.arrival` are the source's currently
     displayed values.
   - Keep the status text separately.
   - Do **not** rename `current` to `actual`, `estimated`, `revised`, or
     "rescheduled" unless the source explicitly provides that meaning.
   - A changed `current` value may be reported as "Trip.com currently shows
     ..." without inventing stronger semantics.

6. **Report the result without reinterpretation.**
   Give the source status first, then scheduled and current times, route/terminal
   fields that are present, and the observation time. Omit unavailable fields.

## Example

For a result containing:

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

Do not turn `23:06` into "actual arrival", "estimated arrival", or "arrival
rescheduled to 23:06" unless Trip.com explicitly identifies it that way.

## Errors and limitations

The CLI uses named errors such as:

- `trip_antibot_challenge`
- `trip_parser_changed`
- `trip_network_error`
- `trip_http_error`
- `trip_operating_date_mismatch`
- `flight_not_found`
- `missing_dependency`

These mean the requested result could not be established from the current
Trip.com integration. They are not evidence that the real-world flight does not
exist or that it is on time.

Do not hide these failures by silently using another provider.

## Check

Before answering:

- flight number and operating date match the requested operation;
- the selected airport/direction is supported by known route context;
- scheduled and current times remain separate;
- Trip.com status wording is not strengthened by inference;
- unavailable fields are omitted rather than guessed;
- Trip.com / VariFlight is identified as the source.

## Stop

Stop before fare search, rebooking, check-in, purchase, compensation, or other
travel actions unless the user separately asks for them.
