---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.6.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

Create an importable `.ics` from private flight evidence through the skill-owned CLI.

## Overview

Normal generation is one CLI-owned `build auto` command. The CLI owns route detection, private output bundle creation, canonical artifact names, and verification.

## Mandatory Runbook

1. Keep the source private. Store credential-bearing URLs or extracted itinerary JSON in a private local file. Do not print source contents or generated `.ics` text.

2. Run exactly one JSON build command.

   ```bash
   SKILL_DIR='<skill_dir returned by skill_view>'
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
   ```

   For canonical itinerary JSON:

   ```bash
   python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
   ```

3. Parse the JSON envelope from stdout or `data.envelope_path`.

4. Require the code-owned handoff: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, `command=build`, `data.agent_handoff.ready=true`, `data.agent_handoff.artifact_inspection_required=false`, and `data.verification.ok=true`.

5. Return `data.agent_handoff.media` plus `data.agent_handoff.safe_summary`. Do not open generated artifacts for reporting.

## Use / Do Not Use

Use for airline booking links, ticket PDFs, route receipts, emails, screenshots, pasted flight segments, or canonical itinerary JSON.

Do not use for flight search, fare comparison, or route planning; load `flight-search` instead. For direct Google Calendar insertion, generate and verify the `.ics` first, then load `google-workspace`.

Do not run `doctor`, read carrier references, inspect generated `.ics`, or try carrier helpers on a successful happy path. Treat post-build reporting as code-owned `data.agent_handoff` extraction.

## Failure Path

Read the JSON error code. Keep the source private. Do not switch routes without new evidence.

Use `diagnose ...` only when `build auto` fails or diagnostics are explicitly requested. Unknown/manual sources should be normalized to private canonical JSON, then retried with `--json build auto --input /private/itinerary.json`.

## Expanded Troubleshooting

- `references/core/itinerary.md` — normalizing PDFs/emails/screenshots/manual segments into canonical JSON (template: `templates/aeroflot-itinerary.example.json`).
- `references/carriers.md` — carrier-specific fixes for Aeroflot, Red Wings, Ural, and Utair; open only after a carrier build fails.
- `references/maintenance/operations.md` — read-only `maint ...` surfaces and refactor rules.

## Operator Notes

Dependencies: `jsonschema` is required (`pip install jsonschema --break-system-packages`).
`curl_cffi` is optional; when installed, carrier requests use a Chrome TLS fingerprint
(helps behind anti-bot gates such as Ngenix). The CLI auto-detects it; `doctor` reports
the active backend in `data.http_transport`. No code changes are needed either way.

- `diagnose doctor`, `diagnose route-detect`, `diagnose validate`, `diagnose bundle-check`, and `diagnose privacy-check` are diagnostic surfaces.
- `maint contracts`, `maint refs registry-check`, `maint source-runtime diff`, and `maint audit` are read-only maintenance surfaces.
- Runtime sync into `~/.hermes/skills/...` requires explicit approval.
- If using `SKILL_DIR`, assign it on a separate shell line before invoking the command.

## Privacy Rules

- Do not expose private booking URLs, booking keys, locators, passenger names, ticket numbers, document/contact/payment data, generated headers, authentication material, or real generated `.ics` text.
- Use `--url-file` for credential-bearing links.
- Keep examples and tests synthetic.
- Send only the verified media file and a safe summary.

## Verification Checklist

- [ ] Source stayed private.
- [ ] Exactly one `--json build auto ...` command ran for normal generation.
- [ ] Envelope passed schema, success, code-owned handoff, and `data.verification.ok=true` checks.
- [ ] Final response copied `data.agent_handoff.media` and `data.agent_handoff.safe_summary` without private identifiers.
