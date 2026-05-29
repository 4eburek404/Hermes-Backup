# Red Wings manage-booking workflow notes

Use this reference when converting Red Wings (`flyredwings.com`) booking links, PDFs, screenshots, or email confirmations into canonical flight-calendar itinerary JSON and `.ics` files.

## Observed frontend/API shape

Red Wings booking is a Websky-powered SPA at:

- `https://flyredwings.com/booking/`
- Russian site pages may link to `https://flyredwings.com/ru/booking`

The booking frontend uses a GraphQL endpoint observed in the page/config:

- `https://wz.webskyx.com/graphql/query/nemo`

A direct email/manage-booking link can use a hash route shaped like:

```text
https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit
```

The SPA route behaves like `/find/:id?/:secret?/submit`:

- `id` = booking locator / PNR-like identifier.
- `secret` = carrier/Websky access secret from the email link; do **not** assume it is merely the passenger surname.
- `Submit`/`submit` triggers automatic lookup with the initial route values.

The frontend lookup calls a GraphQL `FindOrder` mutation/query with fields equivalent to:

```json
{
  "id": "<PNR>",
  "secret": "<SECRET>",
  "saveInProfile": false
}
```

Some already-opened order pages may have a different hash route, for example:

```text
https://flyredwings.com/booking/#/booking/<ORDER_ID>/order
```

Prefer the `/find/<PNR>/<SECRET>/Submit` email link for re-opening the booking from a calendar event when available.

If the agent only has a PDF, screenshot, or already-opened `#/booking/<ORDER_ID>/order` page, it must ask the user for the original email/manage-booking link shaped `#/find/<PNR>/<SECRET>/Submit` before promising a working one-click calendar booking URL. Do not infer `<SECRET>` from the passenger surname, PNR, order ID, or PDF data.

## Extraction and conversion notes

1. Treat the Red Wings page as a JavaScript SPA; do not expect itinerary details in static HTML.
2. If the user supplies only a screenshot/PDF, extract visible fields first and ask for or use a direct manage-booking URL only when needed for missing operational details.
3. If a direct `/find/<PNR>/<SECRET>/Submit` link is available, call the Websky GraphQL lookup rather than scraping rendered DOM.
4. Convert the returned order/segments into the canonical itinerary schema before generating `.ics`:
   - carrier: `Red Wings` / `WZ` as available;
   - flight number, e.g. `WZ 1034`;
   - departure/arrival airport IATA codes and local datetimes;
   - per-airport IANA timezones;
   - status/payment status when useful;
   - baggage/fare/seat/notes only if explicitly present.
5. Save raw API responses and normalized JSON only to deliberate private paths with owner-only permissions.
6. Normal path: use the dedicated `redwings` command. Manual fetch/normalization is now fallback/debug only when the command fails or the source is not a direct manage link.

## Timezone reminders

Red Wings domestic routes often cross Russian timezones. Do not infer arrival timezone from departure timezone.

Known useful examples from a verified case:

- `KUF` / Samara Kurumoch: `Europe/Samara`.
- `SVX` / Ekaterinburg Koltsovo: `Asia/Yekaterinburg`.

Verify unknown airport timezones with `maps` or another trusted source.

## Privacy handling

The manage-booking URL, PNR/order ID, access secret, passenger name, ticket number, phone, email, and document/contact fields are private.

- Include the full direct booking URL in the private `.ics` event when the user wants a working booking link.
- Do **not** repeat the raw URL, PNR, secret, passenger names, ticket numbers, contact details, or document data in chat summaries or logs.
- Redact examples as `<PNR>`, `<SECRET>`, `<ORDER_ID>`, or `[REDACTED]`.
- If displaying extracted PDF/API text to the user, redact booking codes, contacts, passenger names, ticket numbers, and IDs first.

## CLI command

The dedicated CLI subcommand mirrors the existing carrier flows:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json redwings \
  --url '<Red Wings /find/<PNR>/<SECRET>/Submit URL>' \
  --output-json /private/dir/redwings-trip.input.json \
  --output-ics /private/dir/redwings-trip.ics
```

Expected process trace:

`parse_args → parse_redwings_source → load_timezone_map → fetch_redwings_order → convert_to_itinerary → validate_itinerary_schema → validate_itinerary_semantics → build_calendar → validate_ics → write_json → write_ics/skipped → emit_json`

If the command fails because the SPA/API shape changed, use this reference to repair the live-flow converter or fall back to extracting source ticket data into the canonical itinerary schema and running `make`.