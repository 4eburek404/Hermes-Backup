---
name: flight-calendar-ics
description: Use when creating a compact importable .ics calendar file from a supported airline booking URL or a minimal itinerary JSON.
version: 3.00
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, itinerary]
    related_skills: [ocr-and-documents, google-workspace]
---

# Flight Calendar ICS

Create one short `.ics` file for flight calendar import.

## Commands

Booking URL path:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --url-file <private-url-file>
```

Manual itinerary path:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build --input <private-itinerary.json>
```

Optional flags:

```text
--output      output .ics path
--no-alarms   disable reminders
--tz          CODE=Area/City override, only with --url-file
```

Use `templates/itinerary.example.json` for manual JSON. Keep the itinerary minimal:
root `schema_version`, optional `pnr`, `passengers`, `ticket_number`, `booking_url`, and `flights[]`; each flight has `flight_number`, `departure`, `arrival`, optional `aircraft`, optional `status`; each endpoint has `airport`, optional `city`, `local`, `tz`.

## Rules

- URL evidence goes through `--url-file`; do not put private booking URLs directly on argv.
- Run one `--json build` command.
- If stdout has `ok: true`, send the `media` value to the user and stop. Do not open, read, validate, inspect, or rebuild the generated `.ics`.
- If stdout has `ok: false`, answer with the short error message and ask for corrected input only if needed.

## References

- `references/carriers.md` — open only when a carrier build fails or source evidence is ambiguous.
