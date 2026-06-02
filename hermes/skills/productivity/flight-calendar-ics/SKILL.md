---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.4.3
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, flights, calendar, ics, aeroflot, redwings, utair, ural, itinerary]
    related_skills: [ocr-and-documents, maps, google-workspace]
---

# Flight Calendar ICS

## Overview

Create importable `.ics` files from flight booking/ticket data. The default agent surface is one CLI:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json <command> ...
```

The agent's job is deliberately small: classify the source, run the matching CLI command, parse the JSON envelope, verify the `.ics`, and send it to chat. Do **not** reason through airline APIs or scrape helper stdout in the normal path. Open references only when a command fails, a carrier has no subcommand, or manual normalization is required.

If the user asks to insert events directly into Google Calendar rather than receive an `.ics` file, first generate/validate the itinerary here, then load `google-workspace`.

## When to Use

Use this skill when the user asks for a calendar/ICS file from:

- an airline manage-booking link;
- ticket/route receipt PDF, email text, screenshot, or pasted itinerary;
- existing canonical itinerary JSON;
- manual flight segments.

Do **not** use it for flight search, fare comparison, or route planning; load `flight-search` instead. Do not invent missing calendar-critical fields: flight number, local departure/arrival time, airport, timezone, or arrival date.

## Agent Contract

1. Set paths from the skill loader and keep artifacts private:

```bash
SKILL_DIR='<skill_dir returned by skill_view>'
OUT_DIR="$(mktemp -d /tmp/flight-ics.XXXXXX)"
```

2. Determine the carrier/source from explicit evidence: URL domain, carrier name, flight prefix, or user-provided itinerary JSON. Pick **one** relevant route through the command matrix; do not try multiple carriers/helpers opportunistically. If carrier is unclear but a valid itinerary JSON is available, use `make`. If required fields are missing, ask for the ticket/PDF/email text instead of guessing.
3. Run exactly one dispatch command from `## Command Matrix` with `--json`. Save stdout to `$OUT_DIR/envelope.json`; write private JSON/ICS artifacts into `$OUT_DIR`. If that route fails because the source was misclassified, stop with the JSON error and ask for missing evidence; switch routes only after new explicit evidence, not as a surprise fallback.
4. Verify before delivery. Require: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, expected `command`, `data.segments_count >= 1`, output `.ics` exists, `BEGIN:VCALENDAR`, one `BEGIN:VEVENT` per segment, UTC `DTSTART`/`DTEND` values ending in `Z`, no placeholders such as `TBD`/`UNKNOWN`/`None`, and private JSON/ICS artifact mode `0600` when applicable. For carrier commands, `process[].step=load_timezone_map` should report `catalog_source=skill-bundled-travelpayouts-airport-timezones`, `defaults_count=0`, `catalog_timezones_count > 0`, and explicit `--tz` overrides when provided.
5. Deliver only after verification: `MEDIA:/absolute/path/flights.ics`. In chat, summarize segment count and safe route/timing only. Do not repeat PNR keys, full booking URLs, passenger names, document/contact data, ticket numbers, fare/payment data, generated API headers, or bearer tokens.

## Command Matrix

### Aeroflot / SU / URL has `pnrKey` + `pnrLocator`

Use this CLI command directly. Do **not** call `web_extract` or scrape the URL first; the URL parameters are booking credentials and the CLI handles the Aeroflot API/redaction path.

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json aeroflot \
  --url '<AEROFLOT_MANAGE_BOOKING_URL>' \
  --output-json "$OUT_DIR/itinerary.json" \
  --output-ics "$OUT_DIR/flights.ics" | tee "$OUT_DIR/envelope.json"
```

### Ural Airlines / U6 / Ural manage-booking URL or tracker redirect

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json ural \
  --url '<URAL_MANAGE_BOOKING_OR_TRACKER_URL>' \
  --output-json "$OUT_DIR/itinerary.json" \
  --output-ics "$OUT_DIR/flights.ics" | tee "$OUT_DIR/envelope.json"
```

### Utair / UT / Utair order-manage URL

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json utair \
  --url '<UTAIR_ORDER_MANAGE_URL>' \
  --output-json "$OUT_DIR/itinerary.json" \
  --output-ics "$OUT_DIR/flights.ics" | tee "$OUT_DIR/envelope.json"
```

### Existing canonical itinerary JSON, or manually normalized PDF/email/screenshot data

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json make \
  --input '<PATH_TO_ITINERARY_JSON>' \
  --output "$OUT_DIR/flights.ics" | tee "$OUT_DIR/envelope.json"
```

Use `validate` only for a check-only run:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json validate --input '<PATH_TO_ITINERARY_JSON>'
```

### Red Wings / WZ / direct email manage-booking URL

Use this CLI command for a Red Wings/Websky direct email/manage link shaped `#/find/<PNR>/<ACCESS_KEY>/Submit`. Do **not** infer the access key from surname, PNR, ticket data, or already-opened `#/booking/<ORDER_ID>/order` pages.

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json redwings \
  --url '<RED_WINGS_FIND_URL>' \
  --output-json "$OUT_DIR/itinerary.json" \
  --output-ics "$OUT_DIR/flights.ics" | tee "$OUT_DIR/envelope.json"
```

If the user only has a PDF/screenshot/order page, extract the visible flight facts, ask for the direct email/manage link when a working booking URL or missing details are needed, or normalize manually into canonical itinerary JSON and run `make`.

## Canonical Itinerary Minimum

For manual normalization, write provider-agnostic JSON matching `schemas/itinerary.v1.schema.json`. Top-level required keys are `schema_version` and `flights[]`. Each flight segment needs:

- `flight_number`;
- `departure.local`, `departure.airport`, `departure.tz`;
- `arrival.local`, `arrival.airport`, `arrival.tz`.

Optional booking details may be included in the private JSON/ICS when present in the source. The `.ics` should keep operational details useful on a phone, but the chat summary must stay redacted.

### Event content defaults

When generating or modifying calendar rendering, optimize for mobile calendar legibility rather than dumping every normalized field. Prefer passenger + date + city-only route summaries (`<Фамилия Имя> <DD.MM> <город вылета> - <город прилёта> <HH:MM dep> <HH:MM arr>`) when passenger/city data exists. Keep `DESCRIPTION` compact: PNR, ticket number, one date/route/time line, aircraft when present, and booking link. Do not put IATA-only route labels in `SUMMARY` when city names are available. See `references/event-content-format.md` before changing `SUMMARY`, `LOCATION`, `DESCRIPTION`, or alarm text.

## References

Open these only when needed:

- `references/process-and-data-flow.md` — maintenance overview: data layers, flow diagram, command/module decomposition.
- `references/pdf-attachment-layout-extraction.md` — cached PDF/document attachment lookup and Aeroflot-style layout disambiguation notes.
- `references/agent-cli-contract.md` — full JSON envelope, process traces, safety contract, test contract.
- `references/agent-contract-distillation.md` — maintenance rule: keep `SKILL.md` short for small/free models; put provider/API detail in references.
- `references/canonical-itinerary-contract.md` and `references/canonical-itinerary-schema.md` — provider-agnostic input model.
- Aeroflot URL handling is covered by the `aeroflot` command and the CLI contract; no separate reference is needed for the normal path.
- `references/event-content-format.md` — compact mobile-friendly event content policy: passenger/date/city/time `SUMMARY`, short `DESCRIPTION`, and testing expectations for renderer changes.
- `references/travelpayouts-airport-timezones.md` — why carrier commands use the skill-bundled Travelpayouts airport timezone asset over growing local airport maps one code at a time.
- Carrier fallback/debug notes: `references/ural-airlines-manage-booking.md`, `references/utair-manage-booking.md`, `references/redwings-manage-booking.md`, `references/redwings-order-route-vs-email-link-case.md`.
- `references/hardening-review-checks.md` and `references/skill-architecture-notes.md` — maintenance/review only.

## Failure Rules

- `ok=false` with unknown timezone: first check whether `process[].step=load_timezone_map` loaded the skill-bundled Travelpayouts airport timezone asset (`catalog_timezones_count > 0`). If the asset is missing/stale, rebuild `assets/travelpayouts/airport_timezones.json` from the Travelpayouts plugin airport cache using `scripts/travelpayouts_airport_catalog.py`; do not grow local carrier maps. If a verified airport timezone is absent from the asset, rerun once with explicit `--tz CODE=Area/City` (or fix JSON for `make`) and add a regression that protects the asset/catalog path, not a manual fallback map.
- Airline returns browser-check/HTML or SPA shape changed: do not scrape static HTML. Ask for PDF/email/text/screenshot or use the relevant reference for a live-flow repair.
- CLI usage errors with `--json` are still contract envelopes; fix the command instead of reading argparse prose.
- Legacy helper scripts are implementation/compatibility surfaces. Do not use them as the agent path when `flight_calendar_ics.py --json ...` can do the job.

## Common Pitfalls

1. Loading long carrier references before trying the command; this wastes context and hurts small models.
2. Treating local printed times as UTC or using one timezone for all airports.
3. Making one event for a multi-segment trip; use one `VEVENT` per segment.
4. Sending a file without parsing the JSON envelope and checking event count/timestamps.
5. Leaking booking credentials or passenger/ticket data in chat while trying to be helpful.
6. Guessing Red Wings/Websky access secrets from surname/PNR; ask for the direct email/manage link instead.
7. When modifying the CLI/provider commands, skipping `references/hardening-review-checks.md`: new carriers need redaction tests for their exact credential shape and real JSON envelopes validated against the envelope schema.

## Verification Checklist

- [ ] Carrier/source classified from explicit evidence.
- [ ] Single CLI entrypoint used with `--json`.
- [ ] Envelope parsed: `schema_version`, `ok`, `command`, ordered `process`, and safe `data` checked.
- [ ] `.ics` exists; file mode/private path checked where applicable.
- [ ] `VEVENT` count equals `data.segments_count`.
- [ ] `DTSTART`/`DTEND` are UTC `Z` timestamps; no placeholders in final `.ics`.
- [ ] Calendar content includes source booking details when present, but final chat does not leak private identifiers.
- [ ] Telegram final response includes `MEDIA:/absolute/path/flights.ics` and concise import/use instructions.
