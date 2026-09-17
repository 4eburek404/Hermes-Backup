---
name: flight-calendar-ics
description: Create an importable .ics calendar file from a supported airline booking URL or a flight ticket PDF.
version: 3.04
metadata:
  hermes:
    category: travel
    tags: [travel, flights, calendar, ics]
---
# Flight Calendar ICS

Create one importable `.ics` file from a booking URL or flight ticket PDF.

Treat the directory containing this file as `<skill-root>`.
Use `"${HERMES_SKILLS_PYTHON:-python3}"` for bundled Python commands.

## Workflow

Choose the route from the user's source - Booking URL or PDF itinerary.

### Booking URL

1. Store the URL in a private file.
2. Run:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" \
  --json build \
  --url-file <private-url-file>
```

3. If the CLI returns `ok: true`, return the `media` artifact and stop.
4. If the booking route fails or is ambiguous, read `references/carriers.md`.

Do not open the booking URL in a browser before trying the CLI.

### PDF

1. Convert the PDF to Markdown:

```bash
npx -y @firecrawl/anydoc <file.pdf> -o <private-markdown-file>
```

2. If AnyDoc returns usable text, extract the flight facts from it.
3. If the PDF is image-only or AnyDoc returns no usable text:

   * render the PDF pages with PyMuPDF;
   * run Tesseract OCR on the rendered pages;
   * extract the flight facts from the OCR text.
4. Map the extracted facts to the structure in `templates/itinerary.example.json`.
5. Do not invent missing flight data.
6. Save the itinerary as a private temporary JSON file.
7. Run:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" \
  --json build \
  --input <private-itinerary.json>
```

8. If the CLI returns `ok: true`, return the `media` artifact and stop.

The JSON file is an internal intermediate format. It is not a user input.

Do not pass raw Markdown or OCR text directly to the calendar CLI.

## Success

Success requires:

* `ok: true`
* `media`

Return the generated `.ics` artifact with a short confirmation.

After success, stop. Do not reopen, rewrite, validate, or rebuild the generated `.ics`.

## Failure

If required flight data cannot be extracted or validated:

* do not invent missing values;
* do not generate an `.ics` from uncertain data;
* report what required data is missing or unusable.

## Privacy

Do not expose booking URLs, booking credentials, PNRs, passenger names, ticket numbers, temporary JSON, private paths, or `.ics` contents in chat.

## References

* `templates/itinerary.example.json` — itinerary structure used for the PDF route.
* `references/carriers.md` — carrier-specific troubleshooting for booking URL failures.
