# Carrier Notes

Open this file only for troubleshooting a recognized carrier source: `route_input_insufficient` or another carrier-specific build/redirect failure. Do not open it as a fallback for `route_unknown`; the normal path stays one command: `--json build --url '<booking-url>'`. `--url-file` remains an optional backward-compatible source, and `--input` is the PDF itinerary source. Endpoints, payloads, headers, retries, and response mapping are code-owned by `flight_calendar/carriers/` and `flight_calendar/carrier_http.py`.

Common to all carriers: keep credential-bearing URLs private and never expose them in chat, diagnostics, CLI stdout/stderr, or structured errors; manage-booking pages are JavaScript SPAs, so never scrape page HTML for itinerary data; if no live lookup is possible, normalize visible flight facts into minimal itinerary JSON using `templates/itinerary.example.json` and state any limitation (for example, a missing reopen link). The compact public CLI accepts `--url`, `--url-file`, or `--input`; do not use carrier-specific argv. A `route_unknown` error means that the URL source is not a supported trusted booking source; it does not prove that the airline itself is unsupported. Do not guess the carrier from an unknown source. Suggest a PDF itinerary as the fallback.

## Aeroflot

- A `#/search` URL is not a direct booking link; direct links require `pnr_key` and `pnr_locator`. If the user has only locator/surname evidence from a ticket/PDF/email, use minimal itinerary JSON unless they also provide a supported direct booking URL.
- If the source lacks `pnr_key`, do not invent it or ask for values already visible in the source; switch to `--input` when the visible flight facts are enough.
- An "Ngenix browser check" error means Aeroflot's anti-bot gate blocked the request: retry later, or fetch the booking through a real browser session and normalize manually. The adapter requires `curl_cffi` transport; if it is missing, install it into the same Python interpreter used to run the skill CLI.
- Treat `pnr_key` as a booking credential. Writing the direct booking URL inside the private `.ics` is intended behavior; exposing it anywhere else is not.

## Red Wings

- Only the original email/manage link works for live lookup: `https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit`.
- An already-opened order page `#/booking/<ORDER_ID>/order` is not portable, is not a source of `<SECRET>`, and cannot be converted into one.
- `<SECRET>` is a Websky access key, not the passenger surname. Never guess it from surname, PNR, order ID, or ticket data — if the user has only a PDF/screenshot/opened page and wants a reopen link, ask for the original email link.
- Domestic routes can cross timezones; never assume arrival timezone equals departure timezone.

## Ural Airlines

- The canonical manage-booking URL is `https://service.uralairlines.ru/services?pnr=<PNR>&lastName=<SURNAME>`. The URL needs the PNR and passenger surname; the passenger first name is not part of the URL. Tracking parameters are not part of the canonical link.
- Ural booking links from email can be wrapped by `tn-hgl.mckx.ru`. In the observed mail format, the query parameter `u` contains the complete direct booking URL URL-encoded, for example `https://tn-hgl.mckx.ru/.../?u=<encoded https://service.uralairlines.ru/services?...>`.
- The mail wrapper is not an Ural Airlines fingerprint. The CLI first unwraps a supported mail source, then performs ordinary carrier routing on the decoded destination. Ural is identified from the resulting `service.uralairlines.ru` URL.
- Pass either the direct booking URL or the original mail URL through the normal `--url` interface. The agent must not decode `u`, extract credentials, or reconstruct the direct URL itself.
- A link carrying only `pnrOrTicket=` remains unverified for the Reservation flow. Do not treat it as a PNR alias without evidence; the current live Reservation lookup requires a PNR and surname.
- The adapter keeps only deployment configuration (`version`, `API_URL`, and `API_KEY`) in the runtime cache. A cache miss reads the trusted frontend root and its versioned `env/env.json`; a cache hit skips both.
- The Reservation request uses the locally generated time-bucketed `X-Api-Key` and direct `GET Reservation`. Generated keys and booking credentials remain private.

## S7 Airlines

- Evidence is a direct `https://myb.s7.ru/myb/manage-order?...` URL carrying both `bookingId` and `passengerId`; both query values are private booking credentials and must stay in the CLI source or inside the generated `.ics` only.
- S7's entrypoint returns an auto-submit HTML form first; the adapter follows that form with the same session and extracts the embedded `__r_airs_data` payload from the resulting page. Do not scrape arbitrary visible labels when this payload exists.
- The S7 payload usually includes IANA timezones per segment; `--tz CODE=Area/City` remains a fallback if a segment lacks timezone data.
- Ticket number can be absent from S7 manage-order data; this is acceptable because the compact itinerary contract makes it optional.

## Utair

- The canonical manage-booking URL is `https://www.utair.ru/order-manage?rloc=<PNR>&last_name=<SURNAME>`. The observed direct link may also contain `utm_source` and `utm_campaign`; those tracking parameters are not required and are not part of the canonical booking link.
- Booking emails may use the opaque click wrapper `https://click.mail.utair.io/<...>`. Unlike Ural's embedded-`u` wrapper, this URL does not contain the destination or booking credentials, so one HTTP redirect lookup is required to reveal the destination.
- The mail wrapper is not a Utair carrier fingerprint. Source normalization resolves the known HTTPS wrapper once, then ordinary carrier routing runs on the returned URL. Utair is identified only from the resulting `https://www.utair.ru/order-manage?...` URL.
- Pass either the direct booking URL or the original mail-click URL through the normal `--url` interface. The agent must not follow the redirect manually, extract credentials, or reconstruct a direct URL itself.
- The current live API flow uses the booking locator plus passenger surname: OAuth client credentials, then the orders lookup. Cyrillic surnames and URL encoding are supported.
- A smoke run with a fake locator/surname is a safe reachability check: token success plus a redacted "no orders found" confirms the flow without real booking data.
- Baggage is included only when explicit in booking data; it is never inferred from the fare brand.
