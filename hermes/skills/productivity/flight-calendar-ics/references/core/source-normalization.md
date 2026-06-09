# Source Normalization

Use this reference only when `build auto` cannot directly consume the source, or when the source is a document/manual extract rather than a supported carrier URL.

## Inputs

Supported normalization sources include:

- ticket or itinerary PDFs;
- airline emails and receipts;
- screenshots;
- pasted flight segment text;
- unsupported carrier pages;
- operator-supplied segment details.

Keep originals private. Extract only calendar-safe operational fields needed for canonical itinerary JSON.

## PDF/OCR path

1. Try text extraction first.
2. Use OCR only when text extraction is insufficient.
3. Do not print full document text into chat or logs.
4. Resolve ambiguous city names to airports with explicit evidence.
5. Write a private canonical itinerary JSON file.
6. Run `--json build auto --input /private/itinerary.json`.

## Manual normalization checklist

- Confirm every segment has departure/arrival airport, local departure/arrival time, and date.
- Resolve timezone through the airport timezone catalog.
- Preserve multi-segment ordering.
- Treat ambiguous airports, missing year, impossible duration, or mixed timezones as validation failures until resolved.
- Do not include private booking identifiers or passenger/payment/contact/document data in docs, tests, summaries, or committed fixtures.

## Failure handoff

If normalized JSON fails, read the JSON error code and fix the canonical source. Do not switch to a carrier helper unless new source evidence proves that route is appropriate.
