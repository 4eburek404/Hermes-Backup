# Red Wings

Use this file when creating `.ics` from Red Wings (`flyredwings.com`) booking links, PDFs, screenshots, or email confirmations, or when maintaining the Red Wings/Websky adapter.

## Scope

Applicable sources:

- Red Wings direct email/manage-booking URL;
- Red Wings ticket PDF/email/screenshot with visible flight facts;
- Red Wings booking evidence where the user wants a calendar event to reopen the booking.

If no direct manage-booking link is available, generate the `.ics` from visible flight facts and clearly state that a one-click booking URL could not be included.

## Accepted source evidence

Preferred direct source:

```text
https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit
```

The route behaves like `/find/:id?/:secret?/submit`:

- `id` = booking locator / PNR-like identifier;
- `secret` = Websky access secret from the email/manage link; do not assume it is passenger surname;
- `Submit`/`submit` triggers automatic lookup with initial route values.

Already-opened order pages are different:

```text
https://flyredwings.com/booking/#/booking/<ORDER_ID>/order
```

Treat `#/booking/<ORDER_ID>/order` as private evidence that a booking exists, but not as a portable reopen link and not as a source of `<SECRET>`.

If the user supplies only a PDF, screenshot, or already-opened order page and wants a working booking link, ask for the original email/manage-booking link shaped `#/find/<PNR>/<SECRET>/Submit`. Do not infer `<SECRET>` from surname, PNR, order ID, or ticket data.

## Live/API flow

Red Wings booking is a Websky-powered SPA at:

```text
https://flyredwings.com/booking/
https://flyredwings.com/ru/booking
```

The booking frontend uses a GraphQL endpoint observed in page/config:

```text
https://wz.webskyx.com/graphql/query/nemo
```

The direct find route lookup calls a Websky `FindOrder` operation with fields equivalent to:

```json
{
  "id": "<PNR>",
  "secret": "<SECRET>",
  "saveInProfile": false
}
```

Treat the page as a JavaScript SPA; do not expect itinerary details in static HTML. If a direct find link is available, call the Websky lookup rather than scraping rendered DOM.

## Response → canonical itinerary mapping

Convert returned order/segments into canonical itinerary JSON:

- carrier: `Red Wings` / `WZ` as available;
- flight number, for example `WZ 1034`;
- departure/arrival airport IATA codes and local datetimes;
- per-airport IANA timezones;
- status/payment status when useful;
- baggage/fare/seat/notes only if explicitly present.

Do not infer baggage/fare/seat details from absent data.

## CLI command shape

Prefer exact argv from `doctor.data.agent_contract.dispatch_matrix`. Normal shape:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json redwings \
  --url '<Red Wings /find/<PNR>/<SECRET>/Submit URL>' \
  --output-json /private/dir/redwings.input.json \
  --output-ics /private/dir/flights.ics
```

Manual fetch/normalization is fallback/debug only when the command fails or source is not a direct manage link.

## Privacy

Sensitive values:

- manage-booking URL;
- PNR/order ID;
- access secret;
- passenger name;
- ticket number;
- phone/email;
- document/contact fields;
- raw API payloads.

Rules:

- Include the full direct booking URL in the private `.ics` event when the user wants a working booking link.
- Do not repeat raw URL, PNR, secret, passenger names, ticket numbers, contact details, or document data in chat summaries or logs.
- Redact examples as `<PNR>`, `<SECRET>`, `<ORDER_ID>`, or `[REDACTED]`.
- If displaying extracted PDF/API text, redact booking codes, contacts, passenger names, ticket numbers, and IDs first.

## Carrier-specific pitfalls

- `#/find/<PNR>/<SECRET>/Submit` and `#/booking/<ORDER_ID>/order` are not interchangeable.
- Do not guess `<SECRET>` from passenger surname, PNR, order ID, or PDF data.
- If no email/manage link is available, omit the direct booking URL or use only a non-credentialed general manage page and state the limitation.
- Do not scrape static HTML for itinerary data; use the Websky API or manual canonical JSON.
- Red Wings domestic routes can cross timezones; do not infer arrival timezone from departure timezone.

## Verification

- Direct find link is present or limitation is explicitly recorded.
- Adapter output validates as canonical itinerary JSON.
- `.ics` has one `VEVENT` per segment, UTC `DTSTART`/`DTEND`, local times preserved in `DESCRIPTION`, no placeholders, mode `0600`.
- Chat summary redacts booking credentials and personal data.
- Staged documentation uses placeholders and passes a redacted secret scan before commit.
