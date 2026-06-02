# Manual Source Extraction

This file owns extraction from PDFs, emails, screenshots, and manually supplied flight facts into canonical itinerary JSON. It does not own carrier API calls or direct manage-booking deep links.

## Messaging attachment workflow

- Do not ask for manual flight details until available platform-cached documents have been checked.
- In Telegram/Hermes sessions, attached PDFs commonly appear under the Hermes document cache.
- Prefer the newest plausible PDF, then verify it is the right source by:
  - modification time close to the conversation;
  - extracted text contains expected carrier/flight prefix/date/passenger or booking hints;
  - file size/pages look plausible for a ticket or itinerary.
- If multiple candidate PDFs match, compare extracted text snippets and choose the one with explicit evidence for the requested dates/carrier.

## Manual normalization path

If no live carrier command fits but flight facts are known, normalize visible facts to canonical itinerary JSON and run `make`.

Calendar-critical fields:

- flight number;
- departure airport;
- departure local date/time;
- departure timezone;
- arrival airport;
- arrival local date/time and arrival date;
- arrival timezone.

Rules:

- Do not infer a missing arrival date from duration unless the source explicitly provides enough evidence.
- Do not use one timezone for all airports unless the airports actually share it.
- Do not convert local times to UTC in canonical JSON; store ticket-local times plus IANA TZIDs.
- If timezone is unknown, verify through the bundled catalog, a reliable airport/timezone source, or explicit user evidence; do not put `UNKNOWN`/`TBD`.
- Keep optional private details only when useful in the delivered `.ics`; never repeat them in the final chat summary.

Minimal canonical shape:

```json
{
  "schema_version": "flight-calendar-ics-itinerary.v1",
  "flights": [
    {
      "flight_number": "SU1234",
      "departure": {
        "airport": "SVO",
        "local": "2026-06-01T09:15",
        "tz": "Europe/Moscow"
      },
      "arrival": {
        "airport": "LED",
        "local": "2026-06-01T10:45",
        "tz": "Europe/Moscow"
      }
    }
  ]
}
```

Use fictional examples only in references.

## PDF layout disambiguation

Some route receipts repeat dates and airport/time columns. Plain text extraction may place arrival time next to arrival airport while narrative lines make it look like only one time is present.

Recommended pattern:

1. Use PyMuPDF text extraction for initial carrier/date detection.
2. For the page containing target dates, inspect `page.get_text('words')` grouped by approximate `y` coordinate and sorted by `x` coordinate.
3. Reconstruct each flight card by rows:
   - route/cities row;
   - flight-number row;
   - date row: departure date at left, arrival date at arrival column;
   - time row: departure time at left, arrival time at arrival column;
   - airport row: departure airport under left time, arrival airport under arrival time;
   - aircraft/status rows as optional details.
4. Normalize one segment per flight card into canonical itinerary JSON, then use `make`.
5. Keep chat summaries redacted: do not repeat PNR, ticket number, document number, loyalty number, or passenger details unless explicitly necessary.

Example row interpretation with fictional layout coordinates:

```text
y=267: 05 Jun 2026 @ left | 05 Jun 2026 @ arrival column
y=281: 13:10 @ left       | 13:50 @ arrival column
y=285: SVX @ left         | SVO B @ arrival column
```

This maps to `SVX 2026-06-05T13:10 Asia/Yekaterinburg -> SVO 2026-06-05T13:50 Europe/Moscow`, not a UTC time and not a missing arrival time.

## Verification

- Source classified from explicit evidence.
- Canonical itinerary validates against schema and semantic checks.
- One `flights[]` item exists per real flight segment.
- Local times and airport-specific timezones are preserved before UTC conversion.
- `.ics` verification passes through the normal CLI contract.
- Final summary redacts booking credentials and personal data.
