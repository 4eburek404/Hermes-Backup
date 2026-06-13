---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.7.0
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

3. Parse the compact handoff JSON from stdout. The full diagnostic envelope is already saved at `data.envelope_path`; do not read it on a successful happy path.

4. Require the code-owned handoff: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, `command=build`, `data.agent_handoff.ready=true`, `data.agent_handoff.artifact_inspection_required=false`, and `data.agent_handoff.safe_summary.verification_ok=true`.

5. Return `data.agent_handoff.media` plus `data.agent_handoff.safe_summary`. Do not open generated artifacts for reporting.

## Use / Do Not Use

Use for airline booking links, ticket PDFs, route receipts, emails, screenshots, pasted flight segments, or canonical itinerary JSON.

Do not use for flight search, fare comparison, or route planning; load `flight-search` instead. For direct Google Calendar insertion, generate and verify the `.ics` first, then load `google-workspace`.

Do not run `doctor`, read carrier references, inspect generated `.ics`, or try carrier helpers on a successful happy path. Treat post-build reporting as code-owned `data.agent_handoff` extraction.

## Failure Path

### Why "agent crashes" on simple `build auto`

В большинстве случаев это не крах агента, а **контрактный fail CLI до handoff** на одном из слоёв:

1. `infer_build_route(...)` возвращает `route_input_insufficient` / `route_ambiguous` / `route_unknown`.
2. Сетевой fetch/валидация маршрута (`carrier_*`) падает и не даёт `segments_count`.
3. Пост-билд верификация не даёт `ready=true` (например, `verification.ok=false`, `vevent_count`/`segments_count` mismatch, или `ics_mode` не `0600`/`0644`).

Read the JSON error code. Keep the source private. Do not switch routes without new evidence.

Use `diagnose ...` only when `build auto` fails or diagnostics are explicitly requested. Unknown/manual sources should be normalized to private canonical JSON, then retried with `--json build auto --input /private/itinerary.json`.

### Fast triage sequence

- `diagnose route-detect` перед первым `build auto` для URL/флага/комбинации входа:
  - `python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json diagnose route-detect --url "..."`
- `build auto` только если route-кандидат однозначен по evidence.
- On fail read `error.code`, then:
  - `diagnose validate --input <itinerary.json>` (структурная проверка),
  - `diagnose bundle-check --bundle-dir <output_dir>` (проверка артефактов),
  - `diagnose privacy-check --bundle-dir <output_dir>` (если нужно подтвердить отсутствие утечек).

### Success preconditions for handoff (what agent actually checks)

- `schema_version == flight-calendar-ics-cli.v1`
- `ok == true`
- `command == build`
- `data.agent_handoff.ready == true`
- `data.agent_handoff.artifact_inspection_required == false`
- `data.agent_handoff.safe_summary.verification_ok == true`

## Expanded Troubleshooting

- `references/core/itinerary.md` — normalizing PDFs/emails/screenshots/manual segments into canonical JSON (template: `templates/aeroflot-itinerary.example.json`).
- `references/carriers.md` — carrier-specific fixes for Aeroflot, Red Wings, Ural, and Utair; open only after a carrier build fails.
- `references/build-auto-diagnostics.md` — fast-path matrix for `build auto` failures (`route_*` errors, `verification_ok`, и требования `agent_handoff.ready`).
- `references/maintenance/operations.md` — read-only `maint ...` surfaces and refactor rules.
- `references/maintenance/evaluation.md` — cross-model and version-to-version evaluation rules, including direct CLI baselines and privacy-safe comparison fields.
- `references/maintenance/deterministic-runtime-flow.md` — production/eval pattern for weak or non-tool-call-native models: code-owned CLI execution, model only summarizes safe handoff, and pass/fail split by runtime vs model-as-agent layer.
- `references/maintenance/tool-call-smoke.md` — native tool-call preflight for small/new models; separates model-as-agent failures from calendar-skill/runtime regressions.

## Operator Notes

Dependencies: `jsonschema` is required (`pip install jsonschema --break-system-packages`).
`icalendar` is required for VTIMEZONE-capable ICS generation (`pip install icalendar`).
`curl_cffi` is optional; when installed, carrier requests use a Chrome TLS fingerprint
(helps behind anti-bot gates such as Ngenix). The CLI auto-detects it; `doctor` reports
the active backend in `data.http_transport`. No code changes are needed either way.

The `icalendar` library generates VTIMEZONE components automatically via
`Calendar.new(subcomponents=[...]).add_missing_timezones()`. DTSTART/DTEND lines use
TZID parameters (e.g. `DTSTART;TZID=Europe/Moscow:20250620T153000`) so calendar clients
display local departure/arrival times instead of raw UTC.

### ICS format: VTIMEZONE with TZID

The generated `.ics` files use local DTSTART/DTEND with TZID parameters and VTIMEZONE
components — this is the RFC 5545 standard way to represent timezone-aware events.
Verification accepts both `ics_mode` 0600 (private) and 0644 (owner+group readable).

- `diagnose doctor`, `diagnose route-detect`, `diagnose validate`, `diagnose bundle-check`, and `diagnose privacy-check` are diagnostic surfaces. Add `--full-envelope` to a build command only when full diagnostic stdout is explicitly needed.
- Do not introduce a new handoff schema, `output_profile`, or mode taxonomy for the happy path unless measured evidence shows the existing `flight-calendar-ics-cli.v1` handoff cannot express the contract. Prefer the simplest split: default build stdout = delivery handoff; `data.envelope_path` = full diagnostic envelope; `--full-envelope` = diagnostic stdout.
- `maint contracts`, `maint refs registry-check`, `maint source-runtime diff`, and `maint audit` are read-only maintenance surfaces.
- Runtime sync into `~/.hermes/skills/...` requires explicit approval.
- If using `SKILL_DIR`, assign it on a separate shell line before invoking the command.

## Privacy Rules

- Do not expose private booking URLs, booking keys, locators, passenger names, ticket numbers, document/contact/payment data, generated headers, authentication material, or real generated `.ics` text.
- Use `--url-file` for credential-bearing links.
- Keep examples and tests synthetic.
- Send only the verified media file and a safe summary.

## Pitfalls

- **VTIMEZONE DTSTART lines**: DTSTART inside VTIMEZONE blocks has no `Z` suffix and no TZID (e.g. `DTSTART:19700101T000000`). When validating ICS output, only check DTSTART/DTEND lines inside VEVENT blocks. The `bundle.py` verification already does this via `_extract_vevent_blocks()`.
- **`ics_mode` values**: Accept both `"0600"` (UTC-only .ics, backward compat) and `"0644"` (VTIMEZONE format). Schema enum is `["0600", "0644"]`.
- **`vevent_dt_count` vs `utc_datetime_count`**: The verification field was renamed from `utc_datetime_count` to `vevent_dt_count` to reflect that DT lines can now be TZID-qualified, not just UTC. Schema and tests updated accordingly.
- **`icalendar` migration**: `ics_render.py` was rewritten from manual text assembly (prop/ical_escape/fold_line/validate_ics_text ≈200 lines of boilerplate) to `icalendar` library API (Calendar.new, Event.new, Alarm, add_missing_timezones). The migration reference at `references/optimization-icalendar-migration.md` has the full analysis and rationale.

## Verification Checklist

- [ ] Source stayed private.
- [ ] Exactly one `--json build auto ...` command ran for normal generation.
- [ ] Handoff stdout passed schema, success, code-owned handoff, and `data.agent_handoff.safe_summary.verification_ok=true` checks.
- [ ] Final response copied `data.agent_handoff.media` and `data.agent_handoff.safe_summary` without private identifiers.
