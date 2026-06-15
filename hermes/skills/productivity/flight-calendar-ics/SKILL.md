---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 2.04
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

Create an importable `.ics` from private flight evidence through the skill-owned CLI.

## Algorithm

```
! Do NOT open airline websites in a browser or use web_extract. The CLI fetches and parses booking data internally. Just run the build command — one terminal command does everything !
1. RUN:   python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file>
          —or—
          python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --input <private-itinerary.json>

2. PARSE: stdout is JSON. If ok == true:
            → send_message
            → tell user: route, segments, dates from data.agent_handoff.safe_summary
          If ok != true:
            → rm the --url-file (contains credentials)
            → read error.code from stdout; use diagnose route-detect or diagnose validate for retry.

3. DONE.  No further action needed. One terminal command does everything
```

That is the entire happy path. One terminal command → one JSON → one delivery.

## Dependencies

The CLI requires Python packages that are not part of the standard Hermes venv. If the CLI crashes with `ModuleNotFoundError`, install them before retrying:

```bash
pip install icalendar jsonschema cffi
```

## Mandatory Rules

- **One command.** Run `--json build auto` exactly once. Do not run `doctor`, `diagnose`, `stat`, `ls`, `grep`, `cat`, or `test` after a successful build.
