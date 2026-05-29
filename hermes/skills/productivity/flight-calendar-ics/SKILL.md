---
name: flight-calendar-ics
description: Use when creating importable .ics calendar files from airline booking links, tickets, itinerary JSON, PDFs, emails, screenshots, or manually supplied flight segments.
version: 1.4.0
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

2. Determine the carrier/source from explicit evidence: URL domain, carrier name, flight prefix, or user-provided itinerary JSON. If carrier is unclear but a valid itinerary JSON is available, use `make`. If required fields are missing, ask for the ticket/PDF/email text instead of guessing.
3. Run exactly one dispatch command from `## Command Matrix` with `--json`. Save stdout to `$OUT_DIR/envelope.json`; write private JSON/ICS artifacts into `$OUT_DIR`.
4. Verify before delivery. Require: `schema_version=flight-calendar-ics-cli.v1`, `ok=true`, expected `command`, `data.segments_count >= 1`, output `.ics` exists, `BEGIN:VCALENDAR`, one `BEGIN:VEVENT` per segment, UTC `DTSTART`/`DTEND` values ending in `Z`, no placeholders such as `TBD`/`UNKNOWN`/`None`, and private JSON/ICS artifact mode `0600` when applicable.
5. Deliver only after verification: `MEDIA:/absolute/path/flights.ics`. In chat, summarize segment count and safe route/timing only. Do not repeat PNR keys, access secrets, full booking URLs, passenger names, document/contact data, ticket numbers, fare/payment data, generated API headers, or bearer tokens.

## Command Matrix

### Aeroflot / SU / URL has `pnrKey` + `pnrLocator`

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

### Red Wings / WZ / direct email manage-booking URL

Use this only when the link has the route `#/find/<PNR>/<ACCESS_KEY>/Submit`. Do not use an already-opened `#/booking/<ORDER_ID>/order` URL as a substitute; ask for the email/manage link or source ticket data instead.

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json redwings \
  --url '<RED_WINGS_FIND_URL>' \
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

## Canonical Itinerary Minimum

For manual normalization, write provider-agnostic JSON matching `schemas/itinerary.v1.schema.json`. Top-level required keys are `schema_version` and `flights[]`. Each flight segment needs:

- `flight_number`;
- `departure.local`, `departure.airport`, `departure.tz`;
- `arrival.local`, `arrival.airport`, `arrival.tz`.

Optional booking details may be included in the private JSON/ICS when present in the source. The `.ics` should keep operational details useful on a phone, but the chat summary must stay redacted.

## References

Open these only when needed:

- `references/agent-cli-contract.md` — full JSON envelope, process traces, safety contract, test contract.
- `references/agent-contract-distillation.md` — maintenance rule: keep `SKILL.md` short for small/free models; put provider/API detail in references.
- `references/canonical-itinerary-contract.md` and `references/canonical-itinerary-schema.md` — provider-agnostic input model.
- Carrier fallback/debug notes: `references/ural-airlines-manage-booking.md`, `references/utair-manage-booking.md`, `references/redwings-manage-booking.md`, `references/redwings-order-route-vs-email-link-case.md`.
- `references/hardening-review-checks.md` and `references/skill-architecture-notes.md` — maintenance/review only.

## Failure Rules

- `ok=false` with unknown timezone: verify the airport timezone, then rerun with `--tz CODE=Area/City` for carrier commands or fix the JSON timezone for `make`.
- Airline returns browser-check/HTML or SPA shape changed: do not scrape static HTML. Ask for PDF/email/text/screenshot or use the relevant reference for a live-flow repair.
- Red Wings `#/booking/<ORDER_ID>/order` or no access key: ask for the direct `#/find/<PNR>/<ACCESS_KEY>/Submit` email/manage link before promising a one-click booking URL.
- CLI usage errors with `--json` are still contract envelopes; fix the command instead of reading argparse prose.
- Legacy helper scripts are implementation/compatibility surfaces. Do not use them as the agent path when `flight_calendar_ics.py --json ...` can do the job.

## Common Pitfalls

1. Loading long carrier references before trying the command; this wastes context and hurts small models.
2. Treating local printed times as UTC or using one timezone for all airports.
3. Making one event for a multi-segment trip; use one `VEVENT` per segment.
4. Sending a file without parsing the JSON envelope and checking event count/timestamps.
5. Leaking booking credentials or passenger/ticket data in chat while trying to be helpful.
6. Guessing Red Wings/Websky access secrets from surname/PNR/order id; ask for the direct email/manage link instead.

## Verification Checklist

- [ ] Carrier/source classified from explicit evidence.
- [ ] Single CLI entrypoint used with `--json`.
- [ ] Envelope parsed: `schema_version`, `ok`, `command`, ordered `process`, and safe `data` checked.
- [ ] `.ics` exists; file mode/private path checked where applicable.
- [ ] `VEVENT` count equals `data.segments_count`.
- [ ] `DTSTART`/`DTEND` are UTC `Z` timestamps; no placeholders in final `.ics`.
- [ ] Calendar content includes source booking details when present, but final chat does not leak private identifiers.
- [ ] Telegram final response includes `MEDIA:/absolute/path/flights.ics` and concise import/use instructions.
