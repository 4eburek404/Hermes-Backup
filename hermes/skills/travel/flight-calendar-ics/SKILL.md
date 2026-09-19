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

   * `ok: true`: return the `media` artifact and stop.
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

8. If the CLI returns `ok: true`, return the `media` artifact and stop.

The JSON file is an internal intermediate format. It is not a user input.

Do not pass raw Markdown or OCR text directly to the calendar CLI.

## Maintenance (operator-only)

The runtime timezone module only reads `data/airport-timezones.json`. To refresh
that asset from the public Travelpayouts airport catalogs, run from `<skill-root>`:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/update_airport_timezones.py"
```

The updater downloads all three sources into a temporary directory, validates the
JSON arrays and every retained timezone with Python `zoneinfo`, then atomically
replaces the checked-in asset only when the deterministic candidate differs. Raw
upstream catalogs are not stored in the repository. Its stdout is a short JSON
result containing `ok`, `changed`, `timezone_count`, source hashes, and diff
counts.

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

Do not expose booking URLs or booking credentials in the user response,
diagnostic text, CLI stdout/stderr, or structured error messages. Do not expose
PNRs, passenger names, ticket numbers, temporary JSON, private paths, or `.ics`
contents in chat. This skill does not claim to hide booking URLs from platform
observability or Hermes tool traces.

## References

* `templates/itinerary.example.json` — itinerary structure used for the PDF route.
* `references/carriers.md` — carrier-specific troubleshooting for booking URL failures.
