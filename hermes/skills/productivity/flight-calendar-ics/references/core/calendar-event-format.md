# Calendar Event Format

This file owns how flight data appears inside generated `.ics` events: `SUMMARY`, `LOCATION`, `DESCRIPTION`, and alarms. It does not own source extraction, canonical schema, CLI envelope, or carrier APIs.

## Preferred user-facing event shape

For phone calendar usability, keep event text compact and passenger/route focused.

### `SUMMARY`

Shape:

```text
<Фамилия Имя> <DD.MM> <город вылета> - <город прилёта> <HH:MM dep> <HH:MM arr>
```

Example with fictional data:

```text
Иванов Иван 08.06 Москва - Екатеринбург 14:40 19:10
```

Rules:

- Use passenger surname-first name when available.
- Include date, Russian city-only route, and local departure/arrival times.
- Do not use IATA airport codes in the summary when Russian city names are available.
- Do not lead with flight number unless the user explicitly asks for flight-number-first summaries.

### `DESCRIPTION`

Use a short operational block, not a full dump of normalized itinerary fields.

Include only when present:

1. `PNR: <locator>`
2. `Билет: <ticket number>`
3. one route line: `<DD.MM> <dep city> -> <arr city> <HH:MM dep> <HH:MM arr>`
4. `Самолет: <aircraft>`
5. `Бронирование: <booking URL>`

Omit verbose fields by default: carrier, raw IATA route, status, cabin, fare, baggage, notes, and duplicate passenger lists.

### `LOCATION`

Prefer human-readable city route labels over IATA-only labels when city fields are available. Fall back to airport IATA only when no city is available.

## Data availability constraints

Canonical itinerary endpoints guarantee `airport`, `local`, and `tz`. `city` and `terminal` are optional.

Airport names such as `Шереметьево` are not currently guaranteed canonical fields. Do not invent airport names from IATA unless a deliberate airport-name catalog or `airport_name` schema field is added.

Safe endpoint display fallback:

1. city only;
2. airport IATA only as last resort.

## Implementation guidance

The event rendering source of truth is `scripts/make_flight_ics.py`, not individual airline parsers.

Patch renderer helpers for summary/description/location first. Patch carrier adapters only when canonical JSON lacks needed structured data, such as surname-first passenger labels or city names.

Passenger name order is adapter-sensitive. If the provider response exposes separate `surname`/`last_name` and `first_name`, normalize the itinerary passenger label as surname-first. Do not guess by reversing arbitrary full-name strings in the renderer.

## Privacy boundary

Booking identifiers may exist inside private `.ics` artifacts when operationally useful for the user. They must not appear in stdout/stderr/chat summaries. See `privacy-hardening.md` for redaction and artifact rules.

## Test expectations

Add or update tests before implementation:

- `SUMMARY` contains passenger surname-first label, `DD.MM`, Russian city route, and local departure/arrival times.
- `SUMMARY` does not contain the old flight-number + IATA-only pattern when city/passenger data exists.
- `DESCRIPTION` contains only the compact PNR / ticket / route-time / aircraft / booking-link block.
- `DESCRIPTION` no longer includes verbose fields such as `Fare`, `Cabin`, `Status`, baggage, or raw notes unless explicitly requested.
- `LOCATION` uses city route labels when available.
- stdout/stderr/chat summaries remain redacted even when private identifiers are present inside the `.ics`.
