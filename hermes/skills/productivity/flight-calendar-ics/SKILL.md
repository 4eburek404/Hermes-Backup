---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.7.6
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

Create an importable `.ics` from private flight evidence through the skill-owned CLI.

## Mandatory Runbook

1. **Store source privately.** Put credential-bearing URLs or extracted itinerary JSON in a local file. Never print source contents or `.ics` text.

2. **Run one build command:**

   ```bash
   SKILL_DIR='<skill_dir returned by skill_view>'
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
   ```

   For canonical itinerary JSON:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
   ```

3. **Extract from stdout.** The CLI prints a compact JSON to stdout. If `ok` is true, extract `data.agent_handoff.media` (deliverable .ics) and `data.agent_handoff.safe_summary` (route, segments_count, vevent_count, ics_mode). If `ok` is not true, read `error.code` and see `references/build-auto-diagnostics.md`.

4. **Return to user.** Deliver `data.agent_handoff.media` plus `data.agent_handoff.safe_summary`. Then respond to the user with the result — this completes the task.

## Privacy

- Never expose booking URLs, keys, locators, passenger names, ticket/document/contact/payment data, or `.ics` text.
- Use `--url-file` for credential-bearing links.
- Send only the verified media file and a safe summary.

## Pitfalls

- **VTIMEZONE DTSTART lines**: DTSTART inside VTIMEZONE blocks has no `Z` suffix and no TZID. Only check DTSTART/DTEND inside VEVENT blocks.
- **`ics_mode` values**: Accept both `"0600"` and `"0644"`.
- **ICS size with VTIMEZONE**: ~2× larger than UTC-only (e.g. 6763 vs 3228 bytes). Expected.
- **DT fingerprint across versions**: v1.7+ uses TZID parameters instead of UTC Z-suffix. Compare semantic equivalence, not raw line equality.

## Troubleshooting References

- `references/build-auto-diagnostics.md` — failure triage and diagnose commands
- `references/carriers.md` — carrier-specific fixes (open only after a carrier build fails)
- `references/core/itinerary.md` — normalizing PDFs/emails/screenshots into canonical JSON
- `references/optimization-icalendar-migration.md` — icalendar migration rationale
- `references/maintenance/` — operations, evaluation, deterministic-runtime-flow, tool-call-smoke
- `references/evaluation-golden-path.md` — 9-iteration model eval evidence, SKILL.md golden path synthesis

## Operator Notes

Dependencies: `jsonschema`, `icalendar`. `curl_cffi` optional. `SKILL_DIR` on a separate shell line before the command.