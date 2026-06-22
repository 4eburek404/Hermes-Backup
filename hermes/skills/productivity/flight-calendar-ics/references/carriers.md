# Carrier Notes

Open this file only when a carrier `build` fails or the source evidence is ambiguous. The normal path stays one command: `--json build auto` dispatches the route itself. Endpoints, payloads, headers, retries, and response mapping are code-owned by `flight_calendar/carriers/` and `flight_calendar/carrier_http.py`; argv templates are code-owned by `doctor.data.agent_contract.dispatch_matrix`. Sensitive-data classes: `core/privacy-hardening.md`.

Common to all carriers: store credential-bearing URLs in a private file and pass `--url-file`; manage-booking pages are JavaScript SPAs, so never scrape page HTML for itinerary data; if no live lookup is possible, normalize visible flight facts into canonical JSON (`core/itinerary.md`) and state any limitation (for example, a missing reopen link).

## Aeroflot

- A `#/search` URL is not a direct booking link; direct links require a `pnr_key`. The adapter obtains it itself from PNR + surname (name lookup), so locator and surname from a ticket/PDF/email are sufficient evidence — do not re-ask the user for values already visible in the source.
- If the surname lookup is ambiguous, the adapter retries once with the first name; supply it when available.
- An "Ngenix browser check" error means Aeroflot's anti-bot gate blocked the request: retry later, or fetch the booking through a real browser session and normalize manually. The adapter requires `curl_cffi` transport; if it is missing, install it into the same Python interpreter used to run the skill CLI.
- Treat `pnr_key` as a booking credential. Writing the direct booking URL inside the private `.ics` is intended behavior; exposing it anywhere else is not.

## Red Wings

- Only the original email/manage link works for live lookup: `https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit`.
- An already-opened order page `#/booking/<ORDER_ID>/order` is not portable, is not a source of `<SECRET>`, and cannot be converted into one.
- `<SECRET>` is a Websky access key, not the passenger surname. Never guess it from surname, PNR, order ID, or ticket data — if the user has only a PDF/screenshot/opened page and wants a reopen link, ask for the original email link.
- Domestic routes can cross timezones; never assume arrival timezone equals departure timezone.

## Ural Airlines

- Tracker-wrapped links (`u=` / `url=` query parameters) are decoded by the adapter; pass them as-is via `--url-file`.
- A link carrying only `pnrOrTicket=` is a form-prefill signal, not sufficient evidence: the live lookup also needs the passenger surname. A `route_input_insufficient` error here is the correct outcome, not a generator failure — obtain the surname and retry.
- Node.js is required at runtime: the adapter executes the carrier's frontend API-key helper in a sandboxed Node VM. Generated API keys and session keys are credentials.
- Do not hand the adapter local `.env`/`env.json` copies; the normal path reads live frontend config.

## Utair

- Evidence is `rloc` (locator) plus `last_name` from the order-manage URL; Cyrillic surnames and URL-encoding are handled, `utm_*` parameters are ignored. Explicit `--rloc` / `--last-name` work instead of a URL.
- A smoke run with a fake locator/surname is a safe reachability check: token success plus a redacted "no orders found" confirms the flow without real booking data.
- Baggage is included only when explicit in booking data; it is never inferred from the fare brand.
