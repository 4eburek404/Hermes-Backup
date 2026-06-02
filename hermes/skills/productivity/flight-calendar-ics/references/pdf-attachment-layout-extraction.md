# PDF attachment and layout extraction notes

Use this when a user says they already attached a ticket/PDF or when a PDF extraction has duplicated/ambiguous itinerary rows.

## Messaging attachment workflow

- Do not ask for manual flight details until you have checked available platform-cached documents.
- In Telegram/Hermes sessions, attached PDFs commonly appear under the Hermes document cache. Prefer the newest plausible PDF, then verify it is the right source by:
  - modification time close to the conversation;
  - text contains the expected carrier/flight prefix/date/passenger or booking hints;
  - file size/pages look plausible for a ticket or itinerary.
- If multiple candidate PDFs match, compare extracted text snippets and choose the one with explicit evidence for the requested dates/carrier.

## Aeroflot-style PDF layout disambiguation

Some Aeroflot route receipts repeat dates and airport/time columns. Plain text extraction may place arrival time next to the arrival airport while narrative lines can make it look like only one time is present.

Recommended extraction pattern:

1. Use PyMuPDF text extraction for initial carrier/date detection.
2. For the page containing target dates, inspect `page.get_text('words')` grouped by approximate `y` coordinate and sorted by `x` coordinate.
3. Reconstruct each flight card by rows:
   - route/cities row;
   - `Рейс: SU ####` row;
   - date row: departure date at left, arrival date at the arrival column;
   - time row: departure time at left, arrival time at the arrival column;
   - airport row: departure airport under left time, arrival airport under arrival time;
   - aircraft/status rows as optional details.
4. Normalize one segment per flight card into canonical itinerary JSON, then use the `make` command.
5. Keep chat summaries redacted: do not repeat PNR, ticket number, document number, loyalty number, or passenger details unless necessary.

Example row interpretation from an Aeroflot PDF card:

```text
y=267: 05 июн. 2026 @ left | 05 июн. 2026 @ arrival column
y=281: 13:10 @ left       | 13:50 @ arrival column
y=285: SVX @ left         | SVO B @ arrival column
```

This maps to `SVX 2026-06-05T13:10 Asia/Yekaterinburg -> SVO 2026-06-05T13:50 Europe/Moscow`, not a UTC time and not a missing arrival time.
