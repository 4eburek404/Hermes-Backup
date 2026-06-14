---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 3
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
            → send_message(action='send', message='MEDIA:<ics_path>', target='telegram:<chat_id>:<thread_id>')
            → tell user: route, segments, dates from data.agent_handoff.safe_summary
          If ok != true:
            → rm the --url-file (contains credentials)
            → read error.code, open references/build-auto-diagnostics.md, retry or report error.

3. DONE.  No further action needed.
```

That is the entire happy path. One terminal command → one JSON → one delivery.

**Why `--output-dir` is mandatory:** Without it, the CLI writes .ics to a temp directory (`/tmp/flight-ics.XXXX/`). The `data.agent_handoff.media` path will point there, which works for MEDIA: delivery, but the file will not be in the directory the user or harness expects. Always pass `--output-dir`.

## Dependencies

The CLI requires two Python packages that are not part of the standard Hermes venv. If the CLI crashes with `ModuleNotFoundError`, install them before retrying:

```bash
pip install icalendar jsonschema
```

## Mandatory Rules

- **One command.** Run `--json build auto` exactly once. Do not run `doctor`, `diagnose`, `stat`, `ls`, `grep`, `cat`, or `test` after a successful build.
- **No file verification.** The CLI owns verification. If `ok == true`, the .ics is correct. Do not open, stat, or read the .ics file.
- **No manual result writing.** Do not `write_file` a result.json. The JSON on stdout is the result.
- **No chmod needed.** The CLI writes .ics with standard permissions (0644). `send_message` can read it directly. Do not `chmod` after build. See `references/permission-model.md` for rationale and migration notes.
- **Privacy.** Never expose booking URLs, keys, locators, passenger names, ticket/document/contact/payment data, or `.ics` text. Use `--url-file` for credential-bearing links.
- **Delivery: `send_message` tool ONLY — never inline `MEDIA:` in chat text.** Use:
  ```python
  send_message(action='send', message='MEDIA:<ics_path>', target='telegram:<chat_id>:<thread_id>')
  ```
- **Delivery target: use numeric `telegram:<chat_id>:<thread_id>`.** Bare `target="telegram"` delivers to the home channel, NOT the current DM topic. Use `send_message(action='list')` to find the correct IDs.
- **Url-file cleanup.** The `--url-file` contains credential-bearing URLs. Always `rm` it after the CLI finishes, regardless of success or failure.
- **`.ics` must be in `MEDIA_DELIVERY_EXTS`.** The gateway's `gateway/platforms/base.py` defines `MEDIA_DELIVERY_EXTS`. If `.ics` is NOT in this tuple, `extract_media()` ignores `MEDIA:/path/to/file.ics` and the path arrives as literal text. Verify after fresh installs or major upgrades. See `references/ics-media-delivery-fix.md` for diagnostics.
- **Remote Desktop delivery limitation.** When the agent runs on a remote VPS and the user connects via Hermes Desktop, non-image `MEDIA:` files appear as dead `file://` links. Deliver via Telegram instead. See `references/remote-desktop-media-pitfall.md`.