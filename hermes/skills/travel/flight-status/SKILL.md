---
name: flight-status
description: Use when checking the current operational status of a flight or airport board, including delays, cancellations, revised times, terminals, gates, check-in desks, arrivals, departures, or conflicts between live status sources; not for fare search.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    category: travel
    tags: [travel, flights, status, airport, delays, gates]
    related_skills: [flight-search]
    requires_toolsets: [web, terminal]
---

# Flight Status

## Goal

Answer operational flight-status questions from current, source-labelled evidence. Keep this workflow separate from fare search: schedules, delays, gates, terminals, check-in desks, and actual movement are not ticket inventory.

## Steps

1. **Fix the flight identity.** Record the flight number, operating date, and known origin/destination. Flight numbers repeat daily; do not use an undated row as current status. If only an airport is known, determine whether the user needs departures or arrivals and the relevant date/time window.
2. **Check the operational source first.** Prefer the official departure/arrival airport board for terminal, gate, check-in desk, and local airport status. For an exact flight/date at Sheremetyevo, run the bundled `scripts/sheremetyevo.py` CLI before using a browser or third-party tracker. Prefer the operating airline's official status page for cancellation, schedule changes, and carrier instructions. Do not treat a marketing timetable as a live board.
3. **Fallback without hiding the source type.** If official pages are unavailable or block automation, continue with live board/aggregator sources such as Yandex Rasp airport boards, Trip.com flight status, or FlightAware. Label each as official airline, official airport, airport-board aggregator, or flight tracker.
4. **Match the source to the field.** Use the departure airport board for gate and check-in desks; the relevant airport board for terminal and local status; the airline for passenger instructions; a tracker only for movement/history when operational sources do not expose it. Never infer a gate, desk, terminal, or cancellation from route history.
5. **Reconcile conflicts explicitly.** Preserve each source's local time and status wording, record when it was observed, and state the disagreement. Do not silently merge different scheduled, estimated, and actual times. For gate/desks, the airport board has priority; for carrier instructions, the airline has priority. A third-party tracker does not override an official operational display without explaining the conflict.
6. **Report status first.** Give one compact status line, then scheduled versus updated times, airport/terminal/gate/desks when present, source names with observation time, and a short uncertainty note only when evidence is incomplete or conflicting.

## Sheremetyevo Official API

For an exact flight and operating date at SVO, resolve `<skill-root>` as the
directory containing this `SKILL.md` and run:

```bash
python3 "<skill-root>/scripts/sheremetyevo.py" SU1404 --date 2026-07-16
python3 "<skill-root>/scripts/sheremetyevo.py" "SU 1404" --date 2026-07-16 --json
```

The dependency-free CLI queries Sheremetyevo's official public JSON timetable,
then selects the row whose normalized carrier/flight number and `dat` calendar
date exactly match the request. It does not substitute a neighboring operation.
The result preserves the board's literal status, distinguishes scheduled from
revised departure or arrival, and converts route timestamps with the airport
timezones returned by SVO. It also reports terminal, gate, check-in window/desks,
source URL, and the `X-Date-Update` freshness header when available.

Named failures such as `svo_flight_not_found`, `svo_ambiguous_flight`,
`svo_parser_changed`, or `svo_network_error` are evidence limitations, not proof
that the real-world flight does not exist. Use the official airline next, then a
clearly labelled third-party fallback only if needed.

## Trip.com Airport Board

For a current Trip.com airport-board fallback, resolve `<skill-root>` as the
directory containing this `SKILL.md` and run the bundled read-only script:

```bash
python3 "<skill-root>/scripts/trip_board.py" SVO --direction arrivals
python3 "<skill-root>/scripts/trip_board.py" SVO --direction departures
```

The same Python environment must provide `curl_cffi`; otherwise the script
returns `missing_dependency: curl_cffi`. It does not require BeautifulSoup or a
headless browser.

Add `--json` for structured output. The script returns Trip.com's current
date/time slice and first 24 rows with time, flight number, origin/destination,
airline, terminal, and status. It performs public GET requests only and labels
the result as `Trip.com` with data supplied by `VariFlight`; this is a
third-party airport-board aggregator, not official airport confirmation.

If the script reports `trip_antibot_challenge`, `trip_parser_changed`, or another
named error, report that access/parser limitation. Do not turn it into an empty
board or claim that there are no flights. Arbitrary dates, time windows,
pagination, and polling are outside this first version.

## Input

- Best case: flight number plus operating date.
- Optional: departure/arrival airport, local time window, and the exact field needed.
- Airport-board requests need airport identity plus departures/arrivals and date or time window.

## Output

Use a compact source-labelled card:

```text
STATUS — FLIGHT — DATE
Route: ORIGIN → DESTINATION
Scheduled: ...
Updated/actual: ...
Terminal / gate / check-in: ...
Sources checked: ...
Observed: ...
Conflict or limitation: ...
```

Omit unavailable fields rather than filling them from general knowledge. Keep local timezone wording from the source unless the user asks for conversion.

## Check

- Flight number, operating date, and route are mutually consistent.
- Every delay, cancellation, terminal, gate, or desk claim is traceable to a named current source.
- Scheduled, estimated, and actual times remain distinct.
- Source observation time is stated when freshness matters.
- Official-page automation failure is described as a current access/rendering limitation, not as proof that the page or flight is unavailable.
- Third-party evidence is labelled and not presented as official airline or airport confirmation.

## Stop

- Stop before fare search, rebooking, check-in, purchase, or compensation advice unless the user separately requests that task.
- If the date or flight identity is ambiguous enough to select a different operation, ask for the missing value rather than guessing.
- If no current source exposes a requested field, say that it is not shown in the checked sources; do not infer it.

## References

- `scripts/trip_board.py` — read-only Trip.com airport arrivals/departures board.
- `scripts/sheremetyevo.py` — official SVO exact flight/date lookup.
- Other provider URLs and board identifiers are discovered live so stale hardcoded route and station lists do not become a second source of truth.
