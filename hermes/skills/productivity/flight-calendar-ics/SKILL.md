---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 2
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
1. RUN:   python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file> --output-dir <output-dir>
          —or—
          python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --input <private-itinerary.json> --output-dir <output-dir>

2. PARSE: stdout is JSON. If ok == true:
            → chmod 644 the .ics file; cp it to ~/ if under /tmp
            → hermes send --to "telegram:<chat_id>:<thread_id>" "MEDIA:<home_path>"
            → tell user: route, segments, dates from data.agent_handoff.safe_summary
          If ok != true:
            → read error.code, open references/build-auto-diagnostics.md, retry or report error.

3. DONE.  No further action needed.
```

That is the entire happy path. One terminal command → one JSON → one delivery.

**Why `--output-dir` is mandatory:** Without it, the CLI writes .ics to a temp directory (`/tmp/flight-ics.XXXX/`). The `data.agent_handoff.media` path will point there, which works for MEDIA: delivery, but the file will not be in the directory the user or harness expects. Always pass `--output-dir`.

## Mandatory Rules

- **One command.** Run `--json build auto` exactly once. Do not run `doctor`, `diagnose`, `stat`, `ls`, `grep`, `cat`, or `test` after a successful build.
- **No file verification.** The CLI owns verification. If `ok == true`, the .ics is correct. Do not open, stat, or read the .ics file.
- **No manual result writing.** Do not `write_file` a result.json. The JSON on stdout is the result.
- **Privacy.** Never expose booking URLs, keys, locators, passenger names, ticket/document/contact/payment data, or `.ics` text. Use `--url-file` for credential-bearing links.
