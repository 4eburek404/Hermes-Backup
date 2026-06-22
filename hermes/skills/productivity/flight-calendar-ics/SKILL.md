---
name: flight-calendar-ics
description: Creates and delivers importable .ics calendar files for flights through the skill-owned CLI. Use when the user asks for flight calendar import from booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manual flight segments.
version: 2.06
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, airline, booking, ticket, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

Create and deliver an importable `.ics` for flights.

## Contract

The CLI owns fetching, route inference, itinerary validation, ICS generation, artifact verification, and media handoff.

The agent's job is only to provide private input, run one build command, and give a short safe reply after the runtime delivers the file.

Do not inspect, rewrite, validate, redact, refold, reserialize, or summarize the generated `.ics`.

## Inputs

Use this skill for booking URLs, tickets, itinerary JSON, PDFs, emails, screenshots, or manual flight segments.

For a booking URL, save the full private URL to a private temp file and pass it with `--url-file`.

For canonical itinerary JSON, pass it with `--input`.

For PDFs, emails, screenshots, or manual text, first normalize the evidence into canonical itinerary JSON. Do not invent missing flight data.

Do not open airline sites in a browser. Do not use web extraction for booking pages.

## Run exactly once

Booking URL:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file>
```

Canonical itinerary JSON:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --input <private-itinerary.json>
```

Use the real runtime skill directory for `<skill_dir>`.

## Stdout rule

Stdout is the runtime delivery trigger. Leave it exactly as the CLI prints it.

Never redirect, pipe, capture, parse, reprint, or post-process stdout. Do not use `jq`, `tee`, `cat`, shell variables, `echo ok=...`, helper scripts, or a second command to inspect the result.

After a successful build, run no more commands.

## Result handling

On success: let the runtime deliver the `.ics`; reply briefly using only the surfaced safe summary, if available.

On failure: use only the surfaced safe error. Run diagnostics only after failure or explicit user request; otherwise ask for the missing/corrected source data.

Never paste booking URLs, PNRs, access keys, passenger names, ticket numbers, raw carrier data, raw JSON, private paths, diagnostics, or `.ics` contents into chat.

## Dependencies

If the CLI fails with `ModuleNotFoundError`, install dependencies into the same Python interpreter used for the CLI:

```bash
python -m pip install icalendar jsonschema curl_cffi
```

Use `python -m pip`, not bare `pip`.

## Reply

Keep the reply short and in the user's language:

```markdown
Готово: прикрепил `.ics` для импорта в календарь.
```
