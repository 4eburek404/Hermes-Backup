---
name: flight-calendar-ics
description: Use when creating a compact importable .ics calendar file from a supported airline booking URL or a minimal flight itinerary JSON.
version: 3.01
---

# Flight Calendar ICS

## Goal
Create one importable `.ics` file for flight calendar import using cli

## Steps
1. Put the source in a private file: booking URL in a text file, or itinerary data in minimal JSON.
2. For a booking URL, run:
   `python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --url-file <private-url-file>`
3. For itinerary JSON, run:
   `python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --input <private-itinerary.json>`
4. If the result has `ok: true`, return the `media` value and a short success reply.

## Input
- Required: exactly one source, either `--url-file` or `--input`.
- Optional: `--output <path>`, `--no-alarms`, `--tz CODE=Area/City` with `--url-file` only.
- For manual JSON, use `templates/itinerary.example.json`.

## Output
- The `.ics` artifact from the CLI `media` value.
- Short user-facing reply, for example: `Готово: прикрепил .ics для импорта в календарь.`

## Check
- CLI output is JSON with `ok: true`.
- CLI output includes `media`.
- Do not paste booking URLs, PNRs, passenger names, ticket numbers, raw JSON, private paths, or `.ics` contents into chat.

## Stop
- Stop if the source is missing required flight data.
- Stop after success; do not open, inspect, validate, rewrite, or rebuild the generated `.ics`.

## References
- `templates/itinerary.example.json` — open when converting tickets, PDFs, emails, screenshots, or manual segments to canonical itinerary JSON.
- `references/carriers.md` — open when checking supported booking URL routes, carrier notes, or transport dependencies.

## Dependencies
If the CLI fails with ModuleNotFoundError, install dependencies into the same Python interpreter used for the CLI:

python -m pip install icalendar jsonschema curl_cffi
Use python -m pip, not bare pip.
