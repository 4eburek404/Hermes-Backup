# Canonical itinerary JSON contract

## Purpose

`schemas/itinerary.v1.schema.json` is the provider-agnostic input contract for `flight-calendar-ics`. It validates the normalized itinerary consumed by the ICS builder. It does **not** describe raw booking pages, email/PDF extraction output, or carrier API responses.

The response envelope remains separate: `schemas/cli-envelope.v1.schema.json` describes the machine-readable `--json` output of `scripts/flight_calendar_ics.py`.

## Contract layers

1. **Raw source layer** — airline API, booking URL, PDF, email, screenshot, or manual text. This layer may contain provider-specific/private fields.
2. **Adapter layer** — extracts data and maps it to canonical itinerary JSON.
3. **Canonical itinerary layer** — `schema_version: flight-calendar-ics-itinerary.v1`; one `flights[]` item is one flight segment and one generated `VEVENT`.
4. **Semantic validation layer** — checks IANA timezones, local datetime parsing, and arrival after departure after timezone conversion.
5. **ICS layer** — builds `.ics`, validates event count/UTC timestamps/no placeholders, then writes private artifacts.
6. **CLI envelope layer** — emits `flight-calendar-ics-cli.v1` with safe operational summaries only.

## Required canonical fields

Top level:

- `schema_version: flight-calendar-ics-itinerary.v1`
- `flights[]`

Per segment:

- `flight_number`
- `departure.airport`, `departure.local`, `departure.tz`
- `arrival.airport`, `arrival.local`, `arrival.tz`

Optional generic fields include `calendar_name`, `booking_reference`, `passengers`, `links`, `alarms_minutes`, `pnr`, `ticket_number`, `seat`, `baggage`, `cabin`, `fare`, `aircraft`, `status`, `notes`, and `extensions`.

## Execution flow

Manual `validate`/`make` commands:

```text
parse_args
  → load_input
  → normalize_legacy_itinerary
  → validate_itinerary_schema
  → validate_itinerary_semantics
  → build_calendar
  → validate_ics
  → no_write/write_output
  → emit_json
```

Carrier/source adapter commands:

```text
parse source
  → fetch/read raw source
  → convert_to_itinerary
  → normalize_legacy_itinerary
  → validate_itinerary_schema
  → validate_itinerary_semantics
  → build_calendar
  → validate_ics
  → write_json
  → write_ics/skipped
  → emit_json
```

## What JSON Schema checks

- required keys and object shape;
- unknown fields via `additionalProperties: false`;
- `schema_version` const;
- airport code shape;
- local datetime shape;
- arrays and positive alarm integers;
- URI/date-time formats when `jsonschema` runs with `FORMAT_CHECKER`.

## What stays in semantic/runtime validation

- IANA timezone existence via `zoneinfo.ZoneInfo`;
- local datetime parsing;
- `arrival_utc > departure_utc`;
- placeholder-like required values;
- generated `.ics` event count, UTC `DTSTART`/`DTEND`, and no placeholder strings;
- private artifact permissions (`0600`) and stdout/stderr redaction.

## Adapter rule

New source/carrier integrations must not extend the top-level canonical contract with raw API fields. Put source-specific data in the adapter layer or, only when unavoidable and non-sensitive, inside `extensions`.
