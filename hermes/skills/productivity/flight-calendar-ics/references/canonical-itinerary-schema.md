# Canonical itinerary schema notes

Use this reference when maintaining the flight-calendar-ics input contract or adding another airline/source adapter.

## Contract boundary

Keep two schemas separate:

- `schemas/itinerary.v1.schema.json` — provider-agnostic **input itinerary** consumed by the calendar builder.
- `schemas/cli-envelope.v1.schema.json` — machine-readable **CLI response envelope** consumed by agents.

Do not overload the CLI envelope schema with itinerary fields. Carrier-specific raw fields (PNR keys, API headers, SPA tokens, `lastName`, `rloc`, frontend config values, etc.) belong in source adapters and private fetch layers, not in the canonical itinerary schema.

## Recommended flow

```text
raw source / PDF / email / airline API / manual input
  -> source adapter / extractor
  -> canonical itinerary JSON
  -> validate against schemas/itinerary.v1.schema.json
  -> semantic validation in Python
  -> build ICS
  -> validate ICS / RFC 5545 operational checks
  -> emit CLI JSON envelope validated by schemas/cli-envelope.v1.schema.json
```

For carrier commands, save the intermediate JSON only after conversion to the canonical itinerary and successful validation. That makes the `.input.json` artifact reproducible via `make` without live API access.

## Canonical itinerary shape

The top-level object should describe a normalized booking/trip, not a carrier API response:

```json
{
  "schema_version": "flight-calendar-ics-itinerary.v1",
  "calendar_name": "Flights",
  "booking_reference": "ABC123",
  "passengers": ["Ivan Ivanov"],
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
        "gate": "12",
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
      "pnr": "ABC123",
      "ticket_number": "5552400000000",
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

`flights[]` means flight **segments**: one item becomes one `VEVENT`.

## Schema design rules

Use JSON Schema Draft 2020-12:

- include `$schema`, `$id`, `title`, and `$defs`;
- require `schema_version` with `const: "flight-calendar-ics-itinerary.v1"`;
- require top-level `flights` with `minItems: 1`;
- require per-segment `flight_number`, `departure`, and `arrival`;
- require endpoint fields `airport`, `local`, and `tz`;
- set `additionalProperties: false` on canonical objects to catch typos;
- add a controlled `extensions` object on flight segments if provider-specific metadata must survive normalization;
- use `format: uri` for links and `format: date-time` for machine timestamps, but enforce them with `Draft202012Validator.FORMAT_CHECKER`.

Good reusable definitions:

- IATA airport code: `^[A-Z]{3}$`
- carrier/airline code: `^[A-Z0-9]{2,3}$`
- local datetime: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$`
- flight number: `^[A-Z0-9]{2,3}\s?\d{1,4}[A-Z]?$`

## Validation split

JSON Schema should catch structure and type problems:

- missing `flights`;
- missing endpoint timezone;
- bad airport/flight-number shape;
- wrong scalar/list types;
- unknown fields caused by typos.

Python semantic validation should still catch meaning and privacy issues:

- IANA timezone exists via `zoneinfo.ZoneInfo`;
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

Use the canonical helper `scripts/itinerary_contract.py`:

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

## Test expectations

Add/update tests before implementation:

1. `Draft202012Validator.check_schema` accepts the schema.
2. Canonical template(s) validate with the format checker.
3. Invalid examples are rejected: missing `flights`, string `alarms_minutes`, missing `departure.tz`, bad airport code, unknown top-level field.
4. `make` and `validate` process traces include itinerary schema validation before calendar building.
5. Carrier converters output data that validates against `itinerary.v1.schema.json` before writing `.input.json` and `.ics`.
6. CLI output remains redacted and the existing `cli-envelope.v1` contract stays stable.

## External anchors

- JSON Schema Draft 2020-12 is the right schema dialect for `$defs`, conditionals, and modern validator behavior.
- `python-jsonschema` should use `Draft202012Validator.check_schema(...)`, a reusable validator instance, `iter_errors(...)`, and `FORMAT_CHECKER` when `format` enforcement matters.
- RFC 5545/iCalendar concerns belong to ICS validation, not input schema validation: `UID`, `DTSTAMP`, UTC `DTSTART`/`DTEND`, and `DTEND`/`DURATION` exclusivity are calendar-output rules.
