---
name: flight-calendar-ics
description: Create an importable .ics calendar file from a supported airline booking URL or a flight ticket PDF.
version: 3.05
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

1. Run the CLI once with the booking URL as one shell-quoted argument:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/flight_calendar_ics.py" \
  --json build \
  --url '<booking-url>'
```

2. Handle the result by its error code:

   * `ok: true`: follow the single `## Success` contract below.
   * `route_unknown`: stop. Do not guess the carrier, inspect query or fragment
     fields for carrier fingerprints, open the URL in a browser as a fallback,
     rewrite the URL, create carrier-specific argv, or use a nested URL from an
     unknown wrapper. Tell the user that this booking-link type is not
     supported and suggest sending the PDF itinerary; do not claim that the
     airline itself is unsupported.
   * `route_input_insufficient`: the carrier source was recognized, but the URL
     lacks data required for the live lookup. Carrier-specific guidance in
     `references/carriers.md` may be useful here.
   * Other failures from an already recognized supported source: read
     `references/carriers.md` if carrier-specific troubleshooting is needed.

   `references/carriers.md` is troubleshooting guidance, not a mandatory step
   in the normal URL workflow.

Do not open the booking URL in a browser before trying the CLI.
Do not create a temporary URL file or use `write_file`, `mktemp`, `--url-file`,
`--url-stdin`, `echo URL |`, or `printf URL |` for the main agent workflow.
Quote the placeholder as shown because booking URLs may contain `&`, `?`, `#`,
and `=`. The CLI receives the already prepared argv value; do not implement
shell escaping in Python.

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

8. If the CLI returns `ok: true`, follow the single `## Success` contract below.

The JSON file is an internal intermediate format. It is not a user input.

Do not pass raw Markdown or OCR text directly to the calendar CLI.

## Success

When the CLI returns `ok: true` and `media` is present:

1. Copy the exact value of `media` into the final response unchanged, including the
   `MEDIA:` prefix. The final response must contain that exact media value, not a
   filesystem path, Markdown link, code fence, or prose substitute.
2. Do not pass the value to `write_file` or any other tool.
3. Do not reopen, rewrite, validate, copy, or rebuild the generated `.ics`.
4. After emitting that exact media value, stop. Make no further tool calls and add
   no additional success text.

Hermes extracts the `MEDIA:/absolute/path/to/flights.ics` token from the final
response, delivers the existing file as an attachment, and removes the token
from the visible message text. This is the only success delivery flow for both
the Booking URL and PDF routes.

## Failure

If required flight data cannot be extracted or validated:

* do not invent missing values;
* do not generate an `.ics` from uncertain data;
* report what required data is missing or unusable.

## Privacy

Do not expose booking URLs or booking credentials in the user response,
diagnostic text, CLI stdout/stderr, or structured error messages. Do not expose
PNRs, passenger names, ticket numbers, temporary JSON, private paths, or `.ics`
contents as prose in chat. The exact success `MEDIA:` token is the required
delivery protocol; Hermes removes it from visible message text after extracting
the attachment. This skill does not claim to hide booking URLs from platform
observability or Hermes tool traces.

## References

* `templates/itinerary.example.json` — itinerary structure used for the PDF route.
* `references/carriers.md` — carrier-specific troubleshooting for booking URL failures.
* `references/provider-architecture.md` — provider, router, and shared transport boundaries.
