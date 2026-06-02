# Event Content Format Notes

Use this when changing or auditing how flight data appears inside generated `.ics` events (`SUMMARY`, `LOCATION`, `DESCRIPTION`, alarms), especially after user feedback about mobile calendar legibility.

## Preferred user-facing event shape

For phone calendar usability, keep event text compact and passenger/route focused:

- `SUMMARY`: passenger surname-first name + date + Russian city-only route + local departure/arrival times.
  - Shape: `<Фамилия Имя> <DD.MM> <город вылета> - <город прилёта> <HH:MM dep> <HH:MM arr>`.
  - Example: `Орлов Константин 08.06 Москва - Екатеринбург 14:40 19:10`.
  - Do not use IATA airport codes in the summary when Russian city names are available.
  - Do not lead with flight number unless the user explicitly asks for flight-number-first summaries.
- `DESCRIPTION`: short operational block, not a full dump of normalized itinerary fields.
  - Include only:
    1. `PNR: <locator>` when present;
    2. `Билет: <ticket number>` when present;
    3. one route line: `<DD.MM> <dep city> -> <arr city> <HH:MM dep> <HH:MM arr>`;
    4. `Самолет: <aircraft>` when present;
    5. `Бронирование: <booking URL>` when present.
  - Omit verbose fields by default: carrier, raw IATA route, status, cabin, fare, baggage, notes, and duplicate passenger lists.
- `LOCATION`: prefer human-readable city route labels over IATA-only labels when city fields are available.

## Data availability constraints

Canonical itinerary endpoints currently guarantee `airport`, `local`, and `tz`; `city` and `terminal` are optional. Some carrier adapters already populate Russian city names. Airport names such as `Шереметьево` are not currently a guaranteed canonical field, so do not fake them from IATA unless a deliberate airport-name catalog or `airport_name` schema field is added.

Safe fallback order for endpoint display:

1. city only;
2. airport IATA only as a last-resort fallback, preferably not in `SUMMARY` if the user asked for city names.

## Implementation guidance

The event rendering source of truth is `scripts/make_flight_ics.py`, not individual airline parsers. Patch renderer helpers for summary/description/location first, and only patch carrier adapters when the canonical JSON lacks needed structured data (for example surname-first passenger names or airport names).

Passenger name order is adapter-sensitive. If the provider response exposes separate `surname`/`last_name` and `first_name`, normalize the itinerary passenger label as surname-first for calendar summaries instead of guessing by reversing arbitrary full-name strings in the renderer.

## Test expectations

Add or update tests before implementation:

- `SUMMARY` contains passenger surname-first label, `DD.MM`, Russian city route, and local departure/arrival times.
- `SUMMARY` does not contain the old flight-number + IATA-only pattern when city/passenger data exists.
- `DESCRIPTION` contains only the compact PNR / ticket / route-time / aircraft / booking-link block.
- `DESCRIPTION` no longer includes verbose fields such as `Fare`, `Cabin`, `Status`, baggage, or raw notes unless explicitly requested.
- Booking identifiers may exist inside private `.ics` artifacts, but stdout/stderr/chat summaries must remain redacted.
