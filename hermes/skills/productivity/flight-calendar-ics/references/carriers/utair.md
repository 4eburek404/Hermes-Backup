# Utair

Use this file when creating `.ics` from Utair order-manage links or when maintaining the Utair adapter. This file owns Utair-specific URL parsing, OAuth client-credentials token acquisition, orders API lookup, response mapping, and privacy pitfalls.

## Scope

Applicable sources:

- Utair order-manage URL such as `https://www.utair.ru/order-manage?rloc=<PNR>&last_name=<SURNAME>`;
- explicit locator/surname provided by the user;
- Utair PDF/email/screenshot where manual canonical normalization is more appropriate than live lookup.

The goal is not analysis of the page; the normal path is an agent-runnable command that creates a private `.ics` calendar file from live booking data.

## Accepted source evidence

URL rules:

- parse `rloc` as locator/PNR;
- parse `last_name` as passenger surname, preserving URL-decoded Cyrillic;
- ignore `utm_*` and other tracking parameters;
- normalize locator to uppercase;
- return redacted validation errors if required fields are missing.

Explicit fields:

- `--rloc '<PNR>'`;
- `--last-name '<SURNAME>'`.

Do not print raw URL, locator, or surname in errors/stdout/stderr.

## Live/API flow

Utair's manage-booking page is a JavaScript SPA. The itinerary is not present in initial HTML; do not scrape the page body.

Use the observed public frontend/API flow:

1. Obtain a public client-credentials token:
   - `POST https://b.utair.ru/oauth/token`
   - form fields: `client_id=website_client`, `grant_type=client_credentials`
   - browser-like headers are sufficient (`User-Agent`, `Origin: https://www.utair.ru`, `Referer`).
2. Query orders:
   - `GET https://b.utair.ru/api/v3/orders`
   - params: `filters[locator]=<PNR>`, `filters[passenger_lastname]=<LAST_NAME>`
   - bearer authorization header with the token value redacted.
   - browser-like `Origin`/`Referer` headers.
3. Convert returned `future[]` / `past[]` order data into canonical itinerary JSON.
4. Generate `.ics` through the single agent CLI.

A smoke run with fake locator/surname can still be useful: OAuth success plus a redacted “no orders found” response confirms token/API reachability without using real private booking logs. Full live verification requires a valid booking URL and a private execution context.

## Response → canonical itinerary mapping

Observed safe structural fields in live data:

- top-level `future[]` orders exist for upcoming trips;
- `offers[]` contains `brand_code`, `brand_name`, and `segment_id`;
- `services[]` may be empty;
- `available_actions` is a dict.

Conversion should look for common segment/order fields defensively and fail loudly when required calendar fields are absent:

- flight number: carrier/airline code plus flight number, for example `UT` + `281`;
- route: departure and arrival airport codes;
- local times: departure/arrival local ISO fields;
- cities/terminals/status when present;
- passengers and tickets from passenger/ticket arrays when present;
- fare from `offers[].segment_id` matching a segment;
- baggage only when explicitly present. Do not infer baggage from fare brand.

## CLI command shape

Prefer exact argv from `doctor.data.agent_contract.dispatch_matrix`. Normal URL shape:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json utair \
  --url '<Utair order-manage URL>' \
  --output-json /private/dir/utair.input.json \
  --output-ics /private/dir/flights.ics
```

Explicit field shape:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json utair \
  --rloc '<PNR>' \
  --last-name '<SURNAME>' \
  --output-json /private/dir/utair.input.json \
  --output-ics /private/dir/flights.ics
```

Expected process trace:

```text
parse_args -> parse_pnr_source -> load_timezone_map -> fetch_utair_token -> fetch_utair_orders -> convert_to_itinerary -> build_calendar -> validate_ics -> write_json -> write_ics/skipped -> emit_json
```


## Privacy

Sensitive values:

- full manage-booking URL;
- PNR/locator;
- passenger surname/name;
- ticket numbers;
- bearer tokens;
- credential-bearing query strings;
- raw order payloads.

Rules:

- Never echo sensitive values in stdout/stderr/chat summaries.
- Redact `rloc=`, `last_name=`, `lastName=`, `filters[locator]`, `filters[passenger_lastname]`, URL-encoded variants, bearer authorization headers, and 13-digit ticket numbers.
- Write normalized JSON and `.ics` artifacts as owner-only `0600` in deliberate private directories.
- It is acceptable and useful for the private `.ics` itself to contain booking details needed for import/use.

## Carrier-specific pitfalls

- Do not rely on initial HTML scraping; use the public frontend/API flow.
- Do not infer baggage from fare brand; only include baggage when explicit in booking data.
- Do not assume one timezone for all airports.
- Do not stop at an analysis-only answer when the user asks for an agent command; extend the CLI contract and tests so future agents can run one command.
- Do not put real locator/surname/order payloads into shell history, chat logs, or references.
- Use unfolded ICS comparisons in tests when asserting fields, because RFC 5545 line folding can split fields across lines.

## Verification

- `doctor` and schema expose `utair`.
- URL parser handles Cyrillic/URL-encoded `last_name`.
- Mocked OAuth + orders fetch path is covered in tests; live tests avoid printing private values.
- Mocked order response converts to one or more canonical itinerary segments.
- Private JSON/ICS modes are `0600`.
- stdout/stderr envelope does not contain locator, surname, passenger names, ticket numbers, bearer tokens, full booking URLs, or raw order payloads.
- `.ics` has one `VEVENT` per segment, UTC timestamps ending `Z`, and no placeholders.
