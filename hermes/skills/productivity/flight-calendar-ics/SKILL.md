---
name: flight-calendar-ics
description: Creates and delivers importable .ics calendar files for flights through the skill-owned CLI. Use when the user wants calendar import from airline booking links, carrier lookup data, itinerary JSON, tickets, PDFs, emails, screenshots, or manually supplied flight segments.
version: 2.05
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, airline, booking, ticket, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

Create and deliver an importable `.ics` calendar file from private flight evidence.

The CLI is the authority. It performs route inference, carrier fetching, itinerary validation, ICS rendering, bundle creation, artifact verification, and delivery handoff emission. The agent must not duplicate these responsibilities.

Normal delivery is code-owned: prepare private input, run one CLI build command, let the runtime deliver the CLI-produced media, then send a short privacy-safe reply.

## Use this skill when

Use this skill when the user wants a calendar-importable `.ics` for flights from any of these sources:

- airline booking or manage-booking links;
- carrier lookup data such as PNR, locator, surname, or access key;
- canonical itinerary JSON;
- tickets, PDFs, emails, screenshots, or other flight evidence that can be normalized into canonical itinerary JSON;
- manually supplied flight segments.

Do not use this skill for fare search, trip planning, live flight status, airline browsing, or general schedule research.

## Core rule

Run the CLI. Let the CLI validate, build, verify, and hand off the `.ics`. Do not inspect or reprocess the result.

The handoff JSON is a machine transport envelope for the runtime and agent boundary. It is not a request for the agent to audit, parse, transform, validate, summarize, or inspect generated artifacts.

## Input preparation

For a booking URL, write the complete private URL to a temporary private file and pass that file with `--url-file`.

For canonical itinerary JSON, pass the JSON path with `--input`.

For tickets, PDFs, emails, screenshots, or manual segments, first convert the evidence into canonical itinerary JSON using the appropriate document/OCR/manual-normalization workflow. Do not invent airports, dates, times, flight numbers, passenger names, PNRs, ticket numbers, or booking links.

Input preparation may use other skills or tools before this skill is called. Once the input is ready, this skill's normal delivery path is exactly one CLI build command.

## Golden delivery command

Run exactly one of these commands for normal delivery.

Booking URL:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --url-file <private-url-file>
```

Canonical itinerary JSON:

```bash
python "<skill_dir>/scripts/flight_calendar_ics.py" --json build auto --input <private-itinerary.json>
```

Use the actual runtime skill directory in place of `<skill_dir>`. Keep the command shape unchanged.

## Stdout and media handoff contract

Terminal stdout is the plugin delivery trigger surface. Preserve it exactly as emitted by the CLI so the runtime can consume the handoff and attach the media.

Never redirect, pipe, capture, reprint, summarize, or post-process stdout. Forbidden forms include:

- `> "$JSON_OUT"`
- `| jq`
- `| tee`
- `JSON="$(python ...)"`
- `cat "$JSON_OUT"`
- `echo "ok=True"`
- `echo "media=..."`
- a second Python, shell, or helper command that prints `ok=`, `media=`, `summary=`, or similar fields

After the build command returns, do not run another command to inspect stdout, the bundle, the JSON envelope, or the generated `.ics`.

## Success handling

If the runtime/tool result reports delivery-ready success:

1. Let the runtime deliver `data.agent_handoff.media` as the `.ics` attachment. If automatic delivery did not happen but the media pointer is surfaced, attach that media pointer without opening the file.
2. Treat `no_further_action_needed == true` as the stop signal.
3. Reply only from `data.agent_handoff.safe_summary` if the runtime surfaces it.
4. Do not run any more terminal commands.
5. Do not open, inspect, edit, validate, redact, refold, reserialize, rewrite, or regenerate the generated `.ics`.

Use safe summary fields exactly as surfaced. If segment details are needed, use only safe summary fields such as route, segment count, flight number, local departure time, and local arrival time. Omit unavailable fields instead of guessing.

A successful build is complete after one CLI command, one runtime handoff, one `.ics` attachment, and one privacy-safe reply.

## Failure handling

If the CLI or runtime reports failure:

1. Use only the privacy-safe error code and message surfaced by the CLI handoff.
2. Keep private source data private. Do not paste raw booking URLs, PNR keys, passenger names, ticket numbers, raw carrier responses, raw itinerary JSON, generated `.ics` contents, private bundle paths, or diagnostic dumps into chat.
3. If a temporary `--url-file` is no longer needed, delete it. If a diagnostic command still needs the source, recreate a fresh private URL file for that diagnostic or retry and delete it immediately afterward.
4. Run diagnostics only after a failed build or an explicit user request.
5. Use `diagnose route-detect` for source or route inference problems.
6. Use `diagnose validate` for canonical itinerary JSON validation problems.
7. Do not switch from `build auto` to an explicit carrier route without new evidence.
8. After repair, run one new `--json build auto` command and return to the success/failure handling rules.

## Diagnostics boundary

Diagnostic and maintenance commands are not part of normal delivery.

Allowed only after failure or explicit user request:

- `diagnose doctor`
- `diagnose route-detect`
- `diagnose validate`
- `diagnose bundle-check`
- `diagnose privacy-check`
- `diagnose timezone inspect`

Maintenance commands are for development and auditing, not user delivery.

After a successful `build auto`, never run `doctor`, `diagnose`, `maint`, `stat`, `ls`, `grep`, `cat`, validators, cleanup commands, or any other terminal command.

## Privacy rules

The generated `.ics` is the private deliverable. It may intentionally contain the user's own booking data required for calendar import, including passenger name, PNR, ticket number, and booking link when present.

Privacy redaction applies to chat, stdout summaries, errors, logs, and diagnostics. It does not mean redacting the user's `.ics` attachment after a successful build.

For user-facing text, use only `data.agent_handoff.safe_summary` when it is surfaced by the runtime.

Never copy these into chat unless they are explicitly present in `safe_summary`:

- PNRs or booking locators;
- access keys or PNR keys;
- ticket numbers;
- passenger names;
- booking links or full URLs;
- contact, payment, or document data;
- raw itinerary JSON;
- raw carrier responses;
- generated `.ics` contents;
- private bundle paths;
- diagnostic plumbing.

## Dependencies

The CLI requires these Python packages in the same interpreter that runs `scripts/flight_calendar_ics.py`:

```bash
python -m pip install icalendar jsonschema cffi
```

Use `python -m pip`, not bare `pip`. If Hermes Desktop or another runtime uses a virtual environment, install into that environment's Python.

Dependency installation is setup, not delivery. Install dependencies only before the first build in a fresh environment or after `ModuleNotFoundError`. Once dependencies are installed, normal delivery still uses exactly one build command.

## User response

Reply in the user's language. Keep the response short and privacy-safe.

Example:

```markdown
Готово: прикрепил `.ics` для импорта в календарь.

Маршрут: <safe_summary.route>
Сегменты: <safe_summary.segments_count>
```

If the safe summary includes segment details, they may be listed using only safe summary fields:

```markdown
- <flight_number>: <route>, вылет <departure_local>, прилёт <arrival_local>
```

Do not add details from memory, generated files, private diagnostics, or raw source evidence.
