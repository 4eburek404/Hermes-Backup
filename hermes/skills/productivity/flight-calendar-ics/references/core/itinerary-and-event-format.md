# Itinerary and Calendar Event Format

This file owns conceptual canonical-itinerary and user-facing calendar text rules. Exact validation/rendering behavior belongs in schemas, renderer code, and tests.

## Canonical itinerary role

Canonical itinerary JSON is the private, provider-neutral handoff from carrier/manual extraction into calendar generation. Use it when the source is a PDF, email, screenshot, pasted segment list, unsupported carrier, or already-normalized data.

Normal command:

```bash
python scripts/flight_calendar_ics.py --json build auto --input /private/itinerary.json
```

`build make --input ...` remains useful for diagnostics/tests or explicit route selection.

## Required semantic fields

Each flight segment needs enough operational data to render a calendar event:

- carrier/flight number when known;
- departure and arrival airports or unambiguous city→airport mapping;
- local departure and arrival datetimes;
- timezone-resolvable airports;
- optional terminal/gate/status/details only when safe and relevant.

Keep private booking identifiers, passenger identity, ticket/document/contact/payment fields, and carrier authentication data out of canonical JSON unless the schema explicitly requires them for a private adapter. Generated chat summaries must not expose them.

## Validation layers

- JSON schema validates document shape.
- Semantic validation checks airport/time/date/event readiness.
- Bundle verification checks `.ics` event count, UTC timestamps, placeholder-free output, and private artifact modes.

Do not replace these checks with prose inspection or by dumping the generated `.ics`.

## Calendar event text

Calendar events should be operational and import-safe:

- `SUMMARY`: concise flight identity and route.
- `LOCATION`: departure/arrival airport route when available.
- `DESCRIPTION`: safe operational details only.
- Times: UTC `DTSTART`/`DTEND` derived from local airport timezones.
- Alarms: keep deterministic renderer behavior in tests.

Avoid placeholders such as `TBD`, `UNKNOWN`, or Python `None`. If a field is unknown, omit it or fail validation before generation, depending on the contract.
