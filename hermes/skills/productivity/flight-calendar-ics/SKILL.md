---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.4.5
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

## Overview

Create an importable `.ics` from flight evidence. The normal path is the single CLI:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json <command> ...
```

Do not reason through carrier APIs in `SKILL.md`. First ask the CLI for its machine-readable runbook/dispatch matrix; open references only for failures, manual normalization, or maintenance.

## When to Use

Use this skill for airline booking links, ticket PDFs, route receipts, emails, screenshots, pasted flight segments, or canonical itinerary JSON.

Do not use it for flight search, fare comparison, or route planning; load `flight-search`. If the user wants direct Google Calendar insertion, first generate/validate the itinerary here, then load `google-workspace`.

## Golden Path

1. **Prepare evidence and workspace.** If the user already sent a PDF/email/screenshot/link in this conversation, inspect or reuse that source before asking again for PNR, surname, route, or times.

   ```bash
   SKILL_DIR='<skill_dir returned by skill_view>'
   OUT_DIR="$(mktemp -d /tmp/flight-ics.XXXXXX)"
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json doctor > "$OUT_DIR/doctor.json"
   ```

2. **Run exactly one CLI command.** Pick one command from `doctor.json` → `data.agent_contract.dispatch_matrix`; write private artifacts into `$OUT_DIR`; save stdout as `$OUT_DIR/envelope.json`.

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json <command> ... | tee "$OUT_DIR/envelope.json"
   ```

   If no carrier command fits but flight facts are known, normalize to canonical itinerary JSON (`references/core/canonical-itinerary.md`) and run `make`.

3. **Verify and send.** Parse `envelope.json`; require `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, `data.segments_count >= 1`, existing `.ics` mode `0600`, one `VEVENT` per segment, UTC `DTSTART`/`DTEND` ending in `Z`, and no `TBD`/`UNKNOWN`/`None`. Then respond with `MEDIA:/absolute/path/flights.ics` and a safe operational summary only.

Privacy: never print PNR keys, full booking URLs, passenger names, ticket/document/contact/payment data, generated API headers, bearer tokens, or access keys in chat. Those may exist only inside the requested private artifact.

## Failure / Maintenance Gate

- CLI `ok=false`: fix the selected command/source from the JSON error. Switch routes only after new explicit evidence.
- Unknown carrier or manual data: use canonical itinerary JSON + `make`.
- PDF/document extraction ambiguity: open `references/core/manual-source-extraction.md`.
- Missing timezone/catalog issue: open `references/core/timezone-catalog.md`; prefer bundled asset or explicit `--tz`, not local fallback maps.
- Event wording/layout change: open `references/core/calendar-event-format.md` and update renderer tests first.
- Carrier/API/CLI contract change: open `references/core/cli-contract.md`, the relevant carrier file under `references/carriers/`, and `references/core/privacy-hardening.md`; add tests before implementation.
- Source/runtime skill sync or commit evidence: open `references/maintenance/source-runtime-sync.md`.

## References

- `references/registry.md` — owner map for all references; check before adding or renaming support files.
- `references/core/cli-contract.md` — CLI JSON envelope, `doctor.data.agent_contract`, process traces, tests, and dispatch contract.
- `references/core/canonical-itinerary.md` — provider-agnostic manual JSON input and schema/semantic boundary.
- `references/core/calendar-event-format.md` — compact mobile calendar summaries/descriptions.
- `references/core/manual-source-extraction.md` — cached attachment/PDF/email/screenshot extraction notes.
- `references/core/timezone-catalog.md` — timezone asset and override policy.
- `references/core/privacy-hardening.md` — redaction, private artifact permissions, and hardening checks.
- `references/maintenance/source-runtime-sync.md` — source↔runtime parity, cleanup, and commit workflow.
- Carrier references only when needed: `references/carriers/aeroflot.md`, `references/carriers/ural-airlines.md`, `references/carriers/utair.md`, `references/carriers/redwings.md`.

## Common Pitfalls

1. Re-asking for data that was already supplied in an attachment/cache.
2. Trying several carriers/helpers opportunistically instead of selecting one CLI command from evidence.
3. Scraping airline manage-booking URLs or helper stdout instead of using `flight_calendar_ics.py --json`.
4. Sending the `.ics` before parsing the envelope and validating the event count/timestamps/placeholders.
5. Leaking booking credentials or passenger/ticket data in chat summaries.
6. Using one timezone for all airports or adding one-off local timezone maps.
7. Treating Red Wings already-opened order pages as access-key sources; use the direct find link or manual canonical JSON.

## Verification Checklist

- [ ] Source classified from explicit evidence or normalized manually.
- [ ] `doctor` read; exactly one `--json` command run; stdout saved to `envelope.json`.
- [ ] Envelope passed: schema version, `ok=true`, command, process, segment count, safe data.
- [ ] `.ics` exists with mode `0600`; `VEVENT` count equals segment count; UTC `DTSTART`/`DTEND` end in `Z`; no placeholders.
- [ ] Final Telegram response includes `MEDIA:/absolute/path/flights.ics` and no private identifiers.
