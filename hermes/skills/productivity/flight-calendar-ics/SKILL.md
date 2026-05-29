---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline ticket/itinerary data, especially Aeroflot-style tickets, booking confirmations, PDFs, email text, or manually supplied flight segments.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

## Overview

Create RFC 5545 `.ics` calendar files from airline ticket data when the carrier or booking site no longer provides a calendar download. Default output is one calendar event per flight segment with stable UID, UTC start/end timestamps, useful route details, and optional reminders.

The normal deliverable is a local `.ics` file the user can import into a mail/calendar app. If the user explicitly asks to put the flights directly into Google Calendar, load `google-workspace` and use its Calendar workflow after generating/validating the event data.

For agent execution, the preferred contract surface is the single Python entrypoint `scripts/flight_calendar_ics.py --json ...`. It returns a stable JSON envelope with an ordered internal process trace; use that instead of scraping human stdout from lower-level helper scripts. Details: `references/agent-cli-contract.md`.

## When to Use

Use this skill when the user asks to:

- create a calendar file from a ticket, route receipt, itinerary, booking email, PDF, screenshot, or manual flight details;
- replace a missing airline "download to calendar" feature;
- produce an `.ics` attachment for Aeroflot/SU, Utair/UT, Ural Airlines/U6, or other airline flights;
- add flight reminders, PNR/e-ticket/seat/baggage details to calendar events.

Do not use it for flight search or itinerary comparison; load `flight-search` for that. Do not invent missing flight times or airports: ask or verify via ticket text/airline data when the missing field affects calendar correctness.

## Golden Path

1. **Collect source data.** Prefer structured itinerary text, ticket PDF, booking email, or manually supplied fields. For scans/screenshots/PDF extraction, load `ocr-and-documents`; for airport timezone lookup, load `maps` or use a trusted airport/timezone source.
2. **Extract flight segments.** One segment = one VEVENT. Required per segment:
   - flight number/carrier;
   - departure date/time, airport, and timezone;
   - arrival date/time, airport, and timezone;
   - booking URL, passenger full name, PNR, and ticket number when the source contains them.
3. **Normalize local times.** Tickets usually print local departure and local arrival times. Convert to aware datetimes using IANA TZIDs, then write UTC `DTSTART`/`DTEND` into the `.ics`. Keep original local times in the description.
4. **Keep the calendar event operationally complete.** Include the booking URL, PNR, passenger full name, ticket number, route/timing, baggage/seat/fare/status, and carrier details in the `.ics` when present. Do not print PNR keys, full booking URLs, passenger names, ticket/document/contact numbers, or fare/payment data in chat/logs unless explicitly required.
5. **Generate `.ics` through the agent CLI.** Use `scripts/flight_calendar_ics.py --json make ...` as the default executable path. Lower-level scripts are compatibility/implementation surfaces, not the preferred agent contract.
6. **Validate before delivery.** Parse the CLI JSON envelope, require `ok=true`, inspect `process`, check `segments_count`, and verify the `.ics` contains `BEGIN:VCALENDAR`, one `BEGIN:VEVENT` per segment, UTC timestamps ending in `Z`, no placeholder values, readable route/flight summaries, and the expected booking URL/PNR/passenger/ticket fields inside the event. If possible, run a smoke import/open or parse check.
7. **Deliver.** In Telegram, send the file as `MEDIA:/absolute/path/file.ics` and summarize segment count plus route/timing without repeating booking credentials or personal ticket data.

## Input Schema for the CLI

Create a JSON file like `templates/aeroflot-itinerary.example.json` and run the CLI against it.

Top-level keys:

```json
{
  "calendar_name": "Flights",
  "booking_reference": "ABC123",
  "links": ["https://www.aeroflot.ru/ru-ru/pnr?pnrKey=<key>&pnrLocator=ABC123"],
  "passengers": ["Ivan Ivanov"],
  "alarms_minutes": [1440, 180],
  "flights": [
    {
      "carrier": "Аэрофлот",
      "flight_number": "SU1234",
      "departure": {
        "airport": "SVO",
        "city": "Москва",
        "terminal": "B",
        "local": "2026-06-01T09:15",
        "tz": "Europe/Moscow"
      },
      "arrival": {
        "airport": "LED",
        "city": "Санкт-Петербург",
        "terminal": "1",
        "local": "2026-06-01T10:45",
        "tz": "Europe/Moscow"
      },
      "seat": "12A",
      "baggage": "1PC",
      "ticket_number": "5552400000000",
      "pnr": "ABC123",
      "status": "confirmed",
      "notes": "Check-in opens 24h before departure"
    }
  ]
}
```

Required fields are `flight_number`, `departure.local`, `departure.airport`, `departure.tz`, `arrival.local`, `arrival.airport`, and `arrival.tz`. `local` must be ISO-like `YYYY-MM-DDTHH:MM` or `YYYY-MM-DD HH:MM`.

## Agent CLI Usage

From any working directory, use the single Python executable with `--json` so the agent can parse a stable contract instead of human text:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json validate \
  --input /path/to/itinerary.json
```

For supported carrier manage-booking links, prefer the carrier subcommand (`aeroflot`, `ural`, or `utair`) so the CLI can fetch, normalize, save private JSON, and generate the calendar in one traceable workflow.

Then generate the file:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json make \
  --input /path/to/itinerary.json \
  --output /private/dir/aeroflot-trip.ics
```

`validate` writes nothing. `make` validates first, writes the `.ics` with owner-only file mode `0600`, and returns `schema_version: flight-calendar-ics-cli.v1`, `ok`, `command`, ordered `process`, and either `data` or `error`; `--json` usage errors also return this envelope. The internal process for `make` is `parse_args → load_input → build_calendar → validate_ics → write_output → emit_json`. See `references/agent-cli-contract.md` for the agent contract and `references/hardening-review-checks.md` for the review checklist; the lower-level `scripts/make_flight_ics.py` remains a compatibility helper, not the preferred agent-facing contract, and must still write private `.ics` artifacts as `0600`.

## Aeroflot PNR Link Workflow

When the user sends an Aeroflot manage-booking URL with `pnrKey` and `pnrLocator`, do not scrape the JS-rendered page. Use the public manage-booking API discovered from `/sb/pnr/app/ru-ru`:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json aeroflot \
  --url '<Aeroflot PNR URL>' \
  --output-json /private/dir/aeroflot-trip.input.json \
  --output-ics /private/dir/aeroflot-trip.ics
```

The CLI POSTs to `/se/api/app/pnr/view/v3` with JSON keys `pnr_locator`, `pnr_key`, `lang: ru`, `country: ru`, converts `data.legs[].segments[]` into the standard itinerary JSON, validates the generated calendar in memory, then writes owner-only JSON/ICS artifacts. When `--url` is supplied, the full Aeroflot manage-booking URL is copied into top-level `links`, so the generated event contains both a `URL` property and a `Links:` line in `DESCRIPTION`. PNR, passenger name, and ticket number from the API response are also written into the event description.

Operational notes:

- Treat the full URL, PNR locator, PNR key, passenger names, document numbers, and ticket numbers as private in chat/logs. For Aeroflot PNR links, the full booking URL, PNR, passenger full name, and ticket number must be written into the `.ics` so the imported calendar event can reopen the booking and show ticket details on any device.
- Parse the `--json` envelope instead of relying on human stdout. For `aeroflot`, the internal process is `parse_args → parse_pnr_source → load_timezone_map → fetch_aeroflot_pnr → convert_to_itinerary → build_calendar → validate_ics → write_json → write_ics/skipped → emit_json`.
- Aeroflot may intermittently return an Ngenix browser-check HTML page. The CLI uses browser-like headers; if Aeroflot still returns HTML, ask the user for the PDF/text/screenshot or use a real browser session.
- The converter has only a small built-in airport timezone map. If it stops on an unknown airport, verify the airport timezone and rerun with `--tz CODE=Area/City`.
- Always verify UTC `DTSTART`/`DTEND`, event count, JSON envelope `ok=true`, and calendar details: `URL`/`Links`, PNR, passenger name, and ticket number present when supplied by the source.

## Ural Airlines Manage-Booking Workflow

When the user sends a Ural Airlines manage-booking link (`service.uralairlines.ru/?pnr=...&lastName=...`) or a tracking redirect whose `u=` parameter points there, decode the redirect and use the carrier's SPA/API rather than asking for manual flight details immediately.

Use the one-command CLI path:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json ural \
  --url '<Ural Airlines manage-booking URL or tracker redirect>' \
  --output-json /private/dir/ural-trip.input.json \
  --output-ics /private/dir/ural-trip.ics
```

Implementation references:

- `references/ural-airlines-manage-booking.md` — API/reservation fields and privacy notes.
- `references/ural-airlines-live-frontend-flow.md` — live frontend flow using the carrier's current public frontend config instead of a local `.env`/copied `env.json`, including redaction and testing notes.
- `references/ural-airlines-one-command-integration-case.md` — condensed case pattern for carrier-SPA one-command integration, including redirect parsing, frontend-derived headers, private intermediate JSON, TDD checks, and completion proof.

Operational notes:

- The frontend is a JS SPA; the initial HTML will not contain the itinerary. The CLI fetches the current frontend config/bundle at runtime and does not require a local `.env`/copied `env.json` for normal use.
- The observed reservation lookup flow is `POST Session` then `GET Reservation` with `pnrNumber` and `lastName`, plus `X-Session` and frontend-generated `X-Api-Key` headers.
- Do not hard-code obfuscated frontend header values; derive them from the current loaded frontend helper or fall back to user-supplied PDF/text if the carrier changes the bundle. Node.js is required for this helper execution.
- Convert `journey.outboundFlights[]`, `returnFlights[]`, and `separateFlights[]` to standard itinerary segments; map `tickets[].flightReferences[]` to flight reference numbers when adding ticket details.
- Verify airport timezones separately. For example, `SVX=Asia/Yekaterinburg`, `DME=Europe/Moscow`; do not assume one timezone for all segments.
- Keep PNR, passenger names, document/contact data, ticket numbers, full booking URLs, and generated API headers out of chat/log summaries; include operational booking details in the private `.ics` when appropriate.

## Utair Manage-Booking Workflow

When the user sends a Utair manage-booking URL (`www.utair.ru/order-manage?rloc=...&last_name=...`), treat the page as a JavaScript SPA and use the carrier API flow rather than scraping the initial HTML.

Target one-command CLI path:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json utair \
  --url '<Utair order-manage URL>' \
  --output-json /private/dir/utair-trip.input.json \
  --output-ics /private/dir/utair-trip.ics
```

Implementation references:

- `references/utair-manage-booking.md` — confirmed OAuth/orders API flow, source parsing, response mapping, timezone, privacy, and TDD checklist.
- `references/utair-one-command-integration-case.md` — condensed case pattern for converting Utair SPA/API booking access into a tested one-command agent workflow with privacy-preserving artifacts.

Operational notes:

- The observed flow is public client-credentials OAuth (`POST https://b.utair.ru/oauth/token`, `client_id=website_client`, `grant_type=client_credentials`) followed by `GET https://b.utair.ru/api/v3/orders` with `filters[locator]`, `filters[passenger_lastname]`, and `Authorization: Bearer <token>`.
- Parse URL parameters `rloc` and `last_name`; ignore `utm_*`; never echo the raw manage-booking URL, locator, surname, passenger names, ticket numbers, or bearer token in stdout/stderr/chat.
- Convert `future[]`/`past[]` order segments to the standard itinerary JSON before generating `.ics`; save both private JSON and ICS artifacts as owner-only `0600`.
- Map fare information from `offers[].segment_id` where present. Do not infer baggage from fare brand; include baggage only when explicitly present in the booking data.
- Verify per-airport timezones. Confirmed useful defaults include `SVX=Asia/Yekaterinburg` and `KUF=Europe/Samara`; support `--tz CODE=Area/City` overrides for unknown airports.

## Event Content Rules

- `SUMMARY`: `<flight_number> <DEP>→<ARR>` plus carrier when useful, e.g. `SU1234 SVO→LED (Аэрофлот)`.
- `LOCATION`: `<departure airport> → <arrival airport>`; include cities/terminals in `DESCRIPTION`.
- `DTSTART` / `DTEND`: UTC timestamps converted from ticket local times and IANA TZIDs.
- `DESCRIPTION`: include departure/arrival local times, airports, terminals, carrier, flight number, passenger(s), PNR, ticket number, seat, baggage, fare/status, links, and notes if present.
- `UID`: stable hash from flight number + departure local time + route + booking reference.
- `VALARM`: default reminders are 24 hours and 3 hours before departure unless user requests otherwise.

## Quality Bar

A generated calendar is acceptable only if:

- every flight segment has a real departure and arrival instant;
- timezones are explicit or confidently inferred and stated;
- overnight/date-boundary arrivals are handled correctly;
- no placeholder strings like `TBD`, `UNKNOWN`, `None`, or empty airport codes are in the final `.ics`;
- booking URL, PNR, passenger full name, and ticket number are included in the `.ics` when present in the source, while private identifiers are not repeated in chat/logs;
- agent execution used the single CLI entrypoint and the JSON envelope has `ok=true`, expected `command`, ordered `process`, and safe summary fields;
- carrier/API workflows save the normalized standard itinerary JSON before `.ics` generation so the calendar is reproducible without refetching live booking data;
- generated JSON/ICS artifacts containing booking data are written to intentional private paths with owner-only permissions;
- the final message gives path/file attachment and concise import instructions without repeating raw booking credentials or personal ticket data.

## Common Pitfalls

1. **Using the same timezone for both airports by habit.** Arrival can be in a different timezone. Use separate departure and arrival TZIDs.
2. **Writing floating local times.** Floating times shift interpretation between calendar apps. Prefer UTC `Z` timestamps after timezone conversion.
3. **Forgetting arrival date.** Tickets may show `+1` or local next-day arrival. Expand it to the correct calendar date before generation.
4. **Leaking PNR/ticket data into chat.** Put booking URL, PNR, passenger name, and ticket number in the `.ics`; do not repeat raw booking credentials or personal ticket data in the chat summary.
5. **One event for a multi-segment trip.** Use one VEVENT per flight segment so delays, terminals, reminders, and routes stay clear.
6. **Skipping verification because the file is text.** Always parse/check counts and timestamps before sending.
7. **Scraping legacy helper stdout instead of using the contract.** For agent work, call `scripts/flight_calendar_ics.py --json ...` and parse the envelope.
8. **Writing private artifacts to casual shared paths.** Use deliberate private paths; the CLI writes generated JSON/ICS files as `0600`, but the path choice is still part of the privacy decision.

## Verification Checklist

- [ ] Source fields captured with provenance: ticket/email/manual input.
- [ ] Single CLI entrypoint used: `scripts/flight_calendar_ics.py --json validate|make|aeroflot|ural|utair`.
- [ ] JSON envelope parsed: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, expected `command`, ordered `process`, and no private identifiers in stdout/stderr.
- [ ] One VEVENT per flight segment.
- [ ] `DTSTART`/`DTEND` are UTC and end with `Z`.
- [ ] Segment summaries match flight numbers and routes.
- [ ] Local departure/arrival times preserved in description.
- [ ] Reminders match user request or defaults.
- [ ] PNR/e-ticket/passenger/booking-link data handling is intentional.
- [ ] File path exists, owner-only permissions are verified for generated artifacts, and the `.ics` is attached or shared with import instructions.
- [ ] Contract tests still pass after skill/CLI changes: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_flight_calendar_ics_cli`.
