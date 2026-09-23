# Carrier Notes

Open this file only for troubleshooting a recognized carrier source: `route_input_insufficient` or another carrier-specific build/redirect failure. Do not open it as a fallback for `route_unknown`; the normal path stays one command: `--json build --url '<booking-url>'`. `--url-file` remains an optional backward-compatible source, and `--input` is the PDF itinerary source. Endpoints, payloads, headers, retries, and response mapping are code-owned by `flight_calendar/carriers/` and `flight_calendar/carrier_http.py`.

Common to all carriers: keep credential-bearing URLs private and never expose them in chat, diagnostics, CLI stdout/stderr, or structured errors; manage-booking pages are JavaScript SPAs, so never scrape page HTML for itinerary data; if no live lookup is possible, normalize visible flight facts into minimal itinerary JSON using `templates/itinerary.example.json` and state any limitation (for example, a missing reopen link). The compact public CLI accepts `--url`, `--url-file`, or `--input`; do not use carrier-specific argv. A `route_unknown` error means that the URL source is not a supported trusted booking source; it does not prove that the airline itself is unsupported. Do not guess the carrier from an unknown source. Suggest a PDF itinerary as the fallback.

## Aeroflot

- A `#/search` URL is not a direct booking link; direct links require `pnr_key` and `pnr_locator`. If the user has only locator/surname evidence from a ticket/PDF/email, use minimal itinerary JSON unless they also provide a supported direct booking URL.
- If the source lacks `pnr_key`, do not invent it or ask for values already visible in the source; switch to `--input` when the visible flight facts are enough.
- An "Ngenix browser check" error means Aeroflot's anti-bot gate blocked the request: retry later, or fetch the booking through a real browser session and normalize manually. The adapter requires `curl_cffi` transport; if it is missing, install it into the same Python interpreter used to run the skill CLI.
- Treat `pnr_key` as a booking credential. Writing the direct booking URL inside the private `.ics` is intended behavior; exposing it anywhere else is not.

## Red Wings

- Routing is based on the trusted `flyredwings.com/booking/` source and the original URL is passed unchanged to the Red Wings adapter.
- The useful email/manage source is `https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit`. It contains both values needed for live lookup.
- When that link is opened in a browser, Red Wings may replace the fragment with `#/booking/<ORDER_ID>/order`. This is browser state after the original lookup; the CLI does not need to reproduce that transition.
- An already-opened `#/booking/<ORDER_ID>/order` source can still be identified as Red Wings, but it is not a source of `<SECRET>` and cannot be converted back into the original find link.
- `<SECRET>` is a Websky access key, not the passenger surname. Never guess it from surname, PNR, order ID, or ticket data.
- Domestic routes can cross timezones; never assume arrival timezone equals departure timezone.

## Ural Airlines

- A direct `service.uralairlines.ru` booking source routes to Ural Airlines and is passed unchanged to the Ural adapter.
- Ural booking emails may use `tn-hgl.mckx.ru`. In the observed form, its single `u` parameter contains the complete direct Ural booking URL URL-encoded.
- Because `tn-hgl.mckx.ru` does not identify the airline by its own host, routing may inspect the embedded destination only far enough to identify a supported `service.uralairlines.ru` source. The original wrapper URL is still passed unchanged to the Ural adapter.
- The Ural adapter owns wrapper decoding, destination validation, credential extraction, and canonicalization.
- The canonical manage-booking URL is `https://service.uralairlines.ru/services?pnr=<PNR>&lastName=<SURNAME>`. Passenger first name and tracking parameters are not part of the canonical link.
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

- Both `www.utair.ru/order-manage` and the carrier-branded mail source `click.mail.utair.io` route directly to the Utair adapter. The original URL is passed unchanged.
- The canonical manage-booking URL is `https://www.utair.ru/order-manage?rloc=<PNR>&last_name=<SURNAME>`.
- Observed direct links may also contain `utm_source` and `utm_campaign`; those tracking parameters are not required and are not part of the canonical booking link.
- The opaque `click.mail.utair.io/<...>` link does not contain the destination or credentials. The Utair adapter therefore performs one redirect lookup, validates that the result is a supported Utair order-manage URL, then extracts locator and surname.
- Pass either the direct booking URL or the original mail-click URL through the normal `--url` interface. The agent must not follow the redirect manually, extract credentials, or reconstruct a direct URL itself.
- The current live API flow uses the booking locator plus passenger surname: OAuth client credentials, then the orders lookup. Cyrillic surnames and URL encoding are supported.
- A smoke run with a fake locator/surname is a safe reachability check: token success plus a redacted "no orders found" confirms the flow without real booking data.
- Baggage is included only when explicit in booking data; it is never inferred from the fare brand.
