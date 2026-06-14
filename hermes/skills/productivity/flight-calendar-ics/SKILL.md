---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.8.0
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
            → send data.agent_handoff.media to user (this is the .ics file)
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

## Pitfalls

- **VTIMEZONE DTSTART lines**: DTSTART inside VTIMEZONE blocks has no `Z` suffix and no TZID. Only check DTSTART/DTEND inside VEVENT blocks.
- **`ics_mode` values**: Accept both `"0600"` and `"0644"`.
- **ICS size with VTIMEZONE**: ~2× larger than UTC-only (e.g. 6763 vs 3228 bytes). Expected.
- **DT fingerprint across versions**: v1.7+ uses TZID parameters instead of UTC Z-suffix. Compare semantic equivalence, not raw line equality.
- **SKILL_DIR**: Use the path returned by `skill_view` for `<skill_dir>`. Put it on a separate shell line before the command.
- **`--output-dir` is mandatory**: Without it, the CLI writes to a temp directory (`/tmp/flight-ics.XXXX/`). Models do not infer optional CLI arguments from prose — if an arg matters, it must appear in the command template.

## Troubleshooting References

- `references/build-auto-diagnostics.md` — failure triage and diagnose commands
- `references/carriers.md` — carrier-specific fixes (open only after a carrier build fails)
- `references/core/itinerary.md` — normalizing PDFs/emails/screenshots into canonical JSON
- `references/optimization-icalendar-migration.md` — icalendar migration rationale
- `references/maintenance/` — operations, evaluation, deterministic-runtime-flow, tool-call-smoke
- `references/evaluation-golden-path.md` — 9-iteration model eval evidence, SKILL.md golden path synthesis
- `scripts/flight_calendar_ics.py` — deterministic CLI (`--json build auto`)
- `references/maintenance/evaluation-v180-convergence.md` — v1.8.0 convergence milestone: all models reach 1 tool call
- `references/evaluation-v179-results.md` — v1.7.9 eval: 4 models × 3 runs, tool call trajectories, `--output-dir` adoption
- `references/evaluation-v180-results.md` — v1.8.0 eval: 4 models × 1 run, all converge to 1 tool call, explicit `--output-dir`

## Operator Notes

Dependencies: `jsonschema`, `icalendar`. `curl_cffi` optional.