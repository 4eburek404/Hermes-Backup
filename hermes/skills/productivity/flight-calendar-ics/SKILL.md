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

### Delivery stdout contract

Terminal tool-call stdout is the plugin-delivery trigger surface. On the golden path,
stdout must be exactly the JSON emitted by:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file>
```

Do not redirect, capture, pipe, tee, parse, summarize, or replace this stdout.
Specifically forbidden forms include:

- `> "$JSON_OUT"`
- `| jq`
- `| tee`
- `JSON="$(python ...)"`
- a second python command that prints `ok=`, `media=`, or `summary=`
- `cat "$JSON_OUT"`
- `echo "ok=True"`
- `echo "media=..."`

After a successful build, do not run another command to inspect or summarize the
result. Read JSON directly from the terminal tool result. Default `--json build`
stdout is already privacy-safe handoff JSON containing `data.agent_handoff.media`
and `safe_summary`; full diagnostics stay private at `data.envelope_path`.

```
! Do NOT open airline websites in a browser or use web_extract. The CLI fetches and parses booking data internally. Just run the build command — one terminal command does everything !
1. RUN:   python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file>
          —or—
          python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --input <private-itinerary.json>

2. PARSE: stdout is JSON. If ok == true:
            → deliver data.agent_handoff.media as an attachment if the runtime has not already delivered it
            → tell user: route, segments, dates from data.agent_handoff.safe_summary
              (safe_summary.segments has flight_number, route, departure_local, arrival_local for each segment — use these, do not guess)
            → do not read, edit, redact, refold, or reserialize the generated .ics
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
- **Final artifact.** The generated `.ics` is the private deliverable and intentionally contains the user's own booking data needed for calendar import (for example passenger name, PNR, ticket number, and booking link when present). Never redact, sanitize, re-fold, reserialize, or rewrite it after a successful build.
- **Safe reporting only.** Privacy redaction applies to chat/stdout/error reporting, not to the `.ics` attachment. Use only `data.agent_handoff.safe_summary` for the text reply.
