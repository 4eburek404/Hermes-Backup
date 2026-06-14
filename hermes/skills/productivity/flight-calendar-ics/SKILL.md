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
            → chmod 644 the .ics file; cp it to ~/ (home directory) if it is under /tmp
            → deliver via send_message(action='send', message='MEDIA:<home_path>')
            → rm the --url-file (contains credentials)
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
- **Privacy.** Never expose booking URLs, keys, locators, passenger names, ticket/document/contact/payment data, or `.ics` text. Use `--url-file` for credential-bearing links.
- **File permissions before delivery.** The CLI writes .ics with mode `0600` (owner-only). On Telegram and other platforms, `MEDIA:` delivery may silently fail if the gateway process cannot read the file. After a successful build, always `chmod 644 <path>` and, if the file is in `/tmp`, also `cp` it to the user's home directory before sending.
- **Delivery: `hermes send` CLI or `send_message` tool ONLY — never inline `MEDIA:` in chat text.** In streaming sessions (`streamed=True`), the gateway suppresses final-send MEDIA processing when `content_delivered=True`. Inline `MEDIA:/path` in chat text arrives as literal text, not a file. Use one of:
  ```bash
  # CLI (preferred — fresh process, no stale import cache):
  hermes send --to "telegram:<chat_id>:<thread_id>" "MEDIA:/home/user/flights.ics"
  ```
  ```python
  # Tool call (works after gateway restart with patched MEDIA_DELIVERY_EXTS):
  send_message(action='send', message='MEDIA:<home_path>', target='telegram:<chat_id>:<thread_id>')
  ```
- **Delivery target: use numeric `telegram:<chat_id>:<thread_id>`.** Bare `target="telegram"` delivers to the home channel, NOT the current DM topic. The user won't see the file there. Use `send_message(action='list')` to find the current topic's `chat_id:thread_id`, then send to `telegram:<chat_id>:<thread_id>` (e.g. `telegram:254089514:259454`). Human-readable targets like `telegram:Konstantin Orlov / topic 259454 (dm)` also work but numeric form is unambiguous. See `references/telegram-media-delivery-pitfalls.md` for full diagnosis.
- **Url-file cleanup.** The `--url-file` contains credential-bearing URLs. Always `rm` it after the CLI finishes, regardless of success or failure.
- **`.ics` must be in `MEDIA_DELIVERY_EXTS`.** The gateway's `gateway/platforms/base.py` defines `MEDIA_DELIVERY_EXTS` — the set of file extensions that `send_message` recognises as deliverable media attachments. If `.ics` is NOT in this tuple, `extract_media()` ignores `MEDIA:/path/to/file.ics` and the path arrives as literal text instead of a native file attachment. After any fresh install or major version upgrade, verify `.ics` is present in `MEDIA_DELIVERY_EXTS` (search for the tuple in `gateway/platforms/base.py`). If missing, add `".ics", ".ical"` under a `# Calendar` comment and restart the gateway before attempting delivery. Patch location in v0.16.0: line ~1199, after the Presentations section. See `references/ics-media-delivery-fix.md` for full diagnostic chain.
- **After patching base.py, clear `.pyc` cache before gateway restart.** Python's `sys.modules` cache and `__pycache__/*.pyc` files can serve stale bytecode even after source changes. Before `hermes gateway restart`, delete `__pycache__` dirs under `gateway/platforms/` or the stale `extract_media` will still ignore `.ics`. If unsure, verify with `python3 -c "from gateway.platforms.base import MEDIA_DELIVERY_EXTS; print('.ics' in MEDIA_DELIVERY_EXTS)"`. If `hermes send` CLI succeeds but the tool call still delivers text, the in-process import cache is stale — restart fixes it after cache cleanup.
- **Remote Desktop delivery limitation.** When the agent runs on a remote backend (VPS) and the user connects via Hermes Desktop, non-image `MEDIA:` files (`.ics`, `.pdf`, `.txt`, etc.) appear as dead `file://` links in Desktop chat — the path points to the backend, not the client. **Deliver via Telegram** (which uploads from the backend) or offer SCP instead. Do NOT rely on inline Desktop chat for non-image file delivery. See `references/remote-desktop-media-pitfall.md` for root cause, GitHub issues (#44523, #44748), and workarounds.
