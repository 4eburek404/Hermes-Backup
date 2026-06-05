# Canonical Itinerary Contract

This file owns the provider-agnostic itinerary JSON contract consumed by `flight-calendar-ics`. It does not describe raw booking pages, email/PDF extraction output, carrier API responses, or the CLI response envelope.

## Contract boundary

Keep two schemas separate:

- `schemas/itinerary.v1.schema.json` — provider-agnostic input itinerary consumed by the calendar builder.
- `schemas/cli-envelope.v1.schema.json` — machine-readable CLI response envelope consumed by agents.

Do not overload the CLI envelope schema with itinerary fields. Carrier-specific raw fields such as PNR keys, API headers, SPA tokens, `lastName`, `rloc`, frontend config values, or access secrets belong in source adapters and private fetch layers, not in the canonical itinerary schema.

## Contract layers

1. **Raw source layer** — airline API, booking URL, PDF, email, screenshot, or manual text; may contain provider-specific/private fields.
2. **Adapter layer** — extracts source data and maps it to canonical itinerary JSON.
3. **Canonical itinerary layer** — `schema_version: flight-calendar-ics-itinerary.v1`; one `flights[]` item is one flight segment and one generated `VEVENT`.
4. **Semantic validation layer** — checks IANA timezones, local datetime parsing, arrival after departure after timezone conversion, and placeholder absence.
5. **ICS layer** — builds `.ics`, validates event count/UTC timestamps/no placeholders, then writes private artifacts.
6. **CLI envelope layer** — emits `flight-calendar-ics-cli.v1` with safe operational summaries only.

## Required canonical fields

Top level:

- `schema_version: flight-calendar-ics-itinerary.v1`
- `flights[]` with `minItems: 1`

Per segment:

- `flight_number`
- `departure.airport`, `departure.local`, `departure.tz`
- `arrival.airport`, `arrival.local`, `arrival.tz`

Optional generic fields include `calendar_name`, `booking_reference`, `passengers`, `links`, `alarms_minutes`, `pnr`, `ticket_number`, `seat`, `baggage`, `cabin`, `fare`, `aircraft`, `status`, `notes`, and `extensions`.

## Canonical itinerary shape

```json
{
  "schema_version": "flight-calendar-ics-itinerary.v1",
  "calendar_name": "Flights",
  "booking_reference": "<BOOKING_REFERENCE>",
  "passengers": ["<PASSENGER_NAME>"],
  "links": ["https://example.com/manage-booking"],
  "alarms_minutes": [1440, 180],
  "source": {
    "kind": "manual",
    "retrieved_at": "2026-06-01T10:00:00Z"
  },
  "flights": [
    {
      "flight_number": "SU1234",
      "carrier": "Aeroflot",
      "carrier_code": "SU",
      "departure": {
        "airport": "SVO",
        "city": "Moscow",
        "terminal": "B",
        "local": "2026-06-01T09:15",
        "tz": "Europe/Moscow"
      },
      "arrival": {
        "airport": "LED",
        "city": "Saint Petersburg",
        "terminal": "1",
        "local": "2026-06-01T10:45",
        "tz": "Europe/Moscow"
      },
      "status": "confirmed",
      "pnr": "<PNR>",
      "ticket_number": "<TICKET_NUMBER>",
      "seat": "12A",
      "baggage": "1PC",
      "cabin": "economy",
      "fare": "Economy",
      "aircraft": "A320",
      "notes": "Check-in opens 24h before departure",
      "links": ["https://example.com/manage-booking"]
    }
  ]
}
```

The example uses fictional data. Do not paste real PNRs, passenger names, ticket numbers, or personal booking URLs into references.

## Execution flow

Manual `validate`/`make` commands:

```text
parse_args
  -> load_input
  -> normalize_legacy_itinerary
  -> validate_itinerary_schema
  -> validate_itinerary_semantics
  -> build_calendar
  -> validate_ics
  -> no_write/write_output
  -> emit_json
```

Carrier/source adapter commands:

```text
parse source
  -> fetch/read raw source
  -> convert_to_itinerary
  -> normalize_legacy_itinerary
  -> validate_itinerary_schema
  -> validate_itinerary_semantics
  -> build_calendar
  -> validate_ics
  -> write_json
  -> write_ics/skipped
  -> emit_json
```

For carrier commands, save the intermediate JSON only after conversion to canonical itinerary and successful validation. That makes the `.input.json` artifact reproducible via `make` without live API access.

## Schema design rules

Use JSON Schema Draft 2020-12:

- include `$schema`, `$id`, `title`, and `$defs`;
- require `schema_version` with `const: "flight-calendar-ics-itinerary.v1"`;
- require top-level `flights` with `minItems: 1`;
- require per-segment `flight_number`, `departure`, and `arrival`;
- require endpoint fields `airport`, `local`, and `tz`;
- set `additionalProperties: false` on canonical objects to catch typos;
- add controlled `extensions` objects only when provider-specific metadata must survive normalization; extension values must match `$defs.extension_value`, not arbitrary schema-free blobs;
- use `format: uri` for links and `format: date-time` for machine timestamps, enforced with `Draft202012Validator.FORMAT_CHECKER`.

Reusable patterns:

- IATA airport code: `^[A-Z]{3}$`
- carrier/airline code: `^[A-Z0-9]{2,3}$`
- local datetime: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$`
- flight number: `^[A-Z0-9]{2,3}\s?\d{1,4}[A-Z]?$`

## Validation split

JSON Schema catches structure and type problems:

- missing `flights`;
- missing endpoint timezone;
- bad airport/flight-number shape;
- wrong scalar/list types;
- unknown fields caused by typos;
- arrays and positive alarm integers;
- URI/date-time formats when the format checker is used.

Python semantic validation catches meaning and privacy-adjacent output problems:

- IANA timezone exists via `zoneinfo.ZoneInfo`;
- local datetime parses;
- arrival UTC instant is after departure UTC instant;
- no placeholder values like `TBD`, `UNKNOWN`, `None`, or empty airport codes;
- no silent airport timezone guessing;
- one segment equals one event;
- generated `UID` is stable;
- generated ICS has UTC `DTSTART`/`DTEND` ending in `Z`;
- `VEVENT` count equals `len(flights)`;
- private booking credentials do not leak into stdout/stderr/chat;
- private JSON/ICS artifacts are written with owner-only permissions.

## Python implementation pattern

Use `scripts/itinerary_contract.py`:

```python
from jsonschema import Draft202012Validator

_SCHEMA = None
_VALIDATOR = None

def load_itinerary_schema() -> dict:
    ...

def validate_itinerary_schema(data: dict) -> list[str]:
    schema = load_itinerary_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return [format_error(e) for e in sorted(validator.iter_errors(data), key=lambda e: e.path)]

def validate_itinerary_semantics(data: dict) -> list[str]:
    ...
```

Prefer `iter_errors` over first-error `validate()` so CLI envelopes can report actionable validation messages.

## Adapter rule

New source/carrier integrations must not extend the top-level canonical contract with raw API fields. Put source-specific data in the adapter layer or, only when unavoidable and non-sensitive, inside `extensions`.

## Test expectations

Add/update tests before implementation:

1. `Draft202012Validator.check_schema` accepts the schema.
2. Canonical templates validate with the format checker.
3. Invalid examples are rejected: missing `flights`, string `alarms_minutes`, missing `departure.tz`, bad airport code, unknown top-level field.
4. `make` and `validate` process traces include itinerary schema validation before calendar building.
5. Carrier converters output data that validates against `itinerary.v1.schema.json` before writing `.input.json` and `.ics`.
6. CLI output remains redacted and the existing `cli-envelope.v1` contract stays stable.

RFC 5545/iCalendar concerns belong to ICS validation, not input schema validation: `UID`, `DTSTAMP`, UTC `DTSTART`/`DTEND`, and `DTEND`/`DURATION` exclusivity are calendar-output rules.
