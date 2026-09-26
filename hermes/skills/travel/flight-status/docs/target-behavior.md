# Flight Status — target behavior

This document records the current target behavior for the `flight-status` skill.
It describes the work need and expected user-facing behavior. It is not an
implementation description and it does not imply that every item below is
already supported by the current CLI.

## Purpose

The skill is for operational work with today's flights.

The user should be able to ask Hermes about flight operations and receive a
reliable current picture without manually opening a browser and searching the
site.

For the current development stage, Trip.com is the source we are developing
against. Different Trip.com pages/data may be used when needed, including an
airport board and a page for a specific flight.

## Main user intents

The skill must support these user intents for **today**:

1. Show all direct flights on a route.
2. Show all direct flights on a route filtered by airline.
3. Check one specific flight.
4. Check several specific flights.
5. On a separate explicit request, check the inbound/feeder flight whose aircraft
   is expected to continue as the user's flight.

The model may generalize natural-language wording. These are intents, not fixed
prompt templates.

## Meaning of "today"

"Today" is the local calendar date of the departure airport.

The current scope is today only. Tomorrow, arbitrary future dates, and historical
date selection are not current requirements.

## Route scope

- A route means direct flights only.
- If the user specifies an airport, use only that airport.
- If the user specifies a city, include all airports serving that city.
- Do not silently expand an explicitly requested airport to neighboring airports.
- A route query without an airline filter includes all airlines.
- If an airline is specified, include only that airline.

## Route overview

For a route query:

- include **all flights for today** that match the requested scope;
- include completed flights;
- include cancelled flights;
- do not hide flights that are operating normally;
- order flights by their scheduled departure time, from the first flight of the
  day to the last;
- when several destination airports are included because the user requested a
  city, keep one chronological list rather than grouping by airport;
- first give one short overall conclusion about the day's picture;
- then give the individual flights.

The overall conclusion must describe the exact requested set. If the request is
filtered to one airline, the conclusion is about that airline's flights, not
about the whole market on the route.

## Specific-flight queries

For one or several explicitly requested flight numbers:

- do not require the user to provide the route or airport;
- determine today's operation and its route from Trip.com;
- do not add a route-level overall conclusion;
- give the information for each requested flight directly.

Each request is an independent snapshot of the current state. The skill does not
need to compare the result with an earlier check in the conversation.

## Required flight identity

For each flight, provide:

- flight number;
- airline, unless the airline is already the explicit filter for the whole
  request;
- departure airport code + city, for example `SVX Екатеринбург`;
- arrival airport code + city, for example `SVO Москва`.

Terminal is not part of the basic answer.

## Core statuses

The current required status set is deliberately small:

- expected on schedule;
- delayed;
- departed;
- arrived;
- cancelled.

The set can be extended later when real Trip.com data and work needs justify it.

For a future flight whose current information has not moved from the schedule,
the user-facing meaning is:

> На текущий момент рейс ожидается по расписанию.

This describes the current snapshot; it is not a promise that the flight will
ultimately depart on time.

## Time terminology

A flight always has both departure and arrival times.

For each side, distinguish three concepts:

### Scheduled time

The time originally stated in the timetable.

Example: the flight was sold and scheduled to depart at 18:50. Even if it later
moves, 18:50 remains the scheduled departure time.

### Expected time

The current expected departure or arrival time when it differs from the
schedule.

Example:

- scheduled departure: 18:50;
- expected departure: 22:50.

### Actual time

The time the event actually occurred.

Expected time must not be relabelled as actual time.

## Which times are required by flight state

### Not yet departed

Show:

- scheduled departure;
- expected departure;
- scheduled arrival;
- expected arrival;
- status.

### Departed but not yet arrived

Show:

- scheduled departure;
- actual departure;
- scheduled arrival;
- expected arrival;
- status.

### Arrived

Show:

- scheduled departure;
- actual departure;
- scheduled arrival;
- actual arrival;
- status.

### Cancelled

Keep the flight in the day's picture at its scheduled position and show the
cancelled status. Do not remove it from the route overview.

A separate calculated delay duration is not required at this stage.

## Inbound / feeder flight

The feeder flight is the preceding flight whose aircraft is expected to arrive
and then continue as the user's flight.

This is **not** part of the standard route or flight answer. Check it only when
the user explicitly asks.

For a feeder-flight request, provide:

- which flight is bringing the aircraft;
- its route;
- scheduled arrival;
- expected arrival or actual arrival, depending on its current state;
- its status;
- a short conclusion about whether the aircraft currently appears able to arrive
  before the user's flight is due to depart.

The conclusion must be based on current data. It must not turn a likely
connection between rotations into certainty when the source does not establish
that certainty.

When Trip.com exposes a Previous Flight relationship, use the preceding flight's
own specific-flight operation as the source of its current operational status
and times. Parent-page Previous Flight metadata may be stale and must not
override newer operational data from that flight's own page. The relationship
itself still does not prove physical-aircraft identity.

## Source and freshness

For the current development stage, use Trip.com.

For a specific flight or feeder-flight request, additional Trip.com pages may be
used when they provide data beyond the airport board.

Every answer must explicitly show the source and freshness, for example:

- `Источник: Trip.com / VariFlight`
- `Проверено: 17:42, Екатеринбург`

The check time is always presented in the Yekaterinburg time zone, not UTC.

## Output format

The exact visual/text layout is intentionally **not specified yet**.

The model should present the required information clearly and compactly. We will
tighten the presentation format only after seeing real outputs in use.

## Deliberately unresolved

Do not turn these into requirements until we have real evidence:

- how Trip.com represents code-share duplicates;
- what to do if different Trip.com views disagree outside the established
  Previous Flight parent/child precedence;
- behavior for rare status values outside the current five;
- behavior for source edge cases that have not actually been observed;
- a fixed final text/table layout.

