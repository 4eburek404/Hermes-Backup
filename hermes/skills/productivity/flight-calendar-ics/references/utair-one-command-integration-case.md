# Utair one-command calendar integration case

## Use case

A user provides a Utair manage-booking URL such as:

```text
https://www.utair.ru/order-manage?rloc=<PNR>&last_name=<SURNAME>&utm_source=booking_success&utm_campaign=mail_link
```

The goal is not just to analyze the page, but to make an agent-runnable command that creates a private `.ics` calendar file from the live booking data.

## Durable pattern

1. Treat the booking page as a JavaScript SPA; do not rely on initial HTML scraping.
2. Parse source credentials from the URL:
   - `rloc` → locator/PNR;
   - `last_name` → passenger surname, preserving URL-decoded Cyrillic;
   - ignore `utm_*` parameters.
3. Use Utair's observed public API flow:
   - `POST https://b.utair.ru/oauth/token`
   - form/body includes `client_id=website_client` and `grant_type=client_credentials`;
   - then `GET https://b.utair.ru/api/v3/orders` with filters for locator/passenger surname and a bearer authorization header; do not record or print the bearer value.
4. Convert returned `future[]` / `past[]` orders into the skill's standard itinerary JSON before building ICS.
5. Generate through the stable agent contract:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json utair \
  --url '<Utair order-manage URL>' \
  --output-json /private/dir/utair-trip.input.json \
  --output-ics /private/dir/utair-trip.ics
```

## Privacy and output shape

- The `.ics` and normalized JSON are intentionally private artifacts and should be written as owner-only `0600`.
- The generated `.ics` should include operational booking details when present: booking link, PNR, passenger name, ticket number, fare/status/seat/baggage.
- Agent stdout/stderr and chat summaries must not echo:
  - raw URL;
  - PNR/locator;
  - surname or passenger full name;
  - ticket/document/contact numbers;
  - bearer token;
  - raw order payload.
- The JSON envelope should expose only safe summary fields: segment count, route list, and artifact paths.

## TDD/checklist that proved useful

Add tests before implementation for:

- `doctor`/schema exposing the new `utair` command;
- URL parsing with Cyrillic `last_name`;
- mocked OAuth + orders fetch path;
- private file mode for generated JSON/ICS;
- no private identifiers in envelope/process/error text;
- `.ics` contains the private operational details inside the file, not in chat;
- unfolded ICS comparisons, because RFC 5545 line folding can split fields across lines.

Run the focused test suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_flight_calendar_ics_cli
```

## Verification notes

- A smoke run with fake locator/surname is still useful: OAuth success plus `no Utair orders found` confirms the token/API path is reachable while avoiding real private booking logs.
- Full live verification requires a valid booking URL. If using a real URL, avoid putting it directly in long-lived shell history or chat logs; prefer private execution context and redacted final summary.
- Verify UTC `DTSTART`/`DTEND`, one `VEVENT` per segment, no placeholders, artifact existence, owner-only permissions, and redacted stdout/stderr before telling the user it is ready.

## Pitfalls

- Do not infer baggage from fare brand; only include baggage when explicit in booking data.
- Do not assume one timezone for all airports; keep `--tz CODE=Area/City` override support for unknown airports.
- Do not stop at an analysis-only answer when the user asks for an agent command; extend the CLI contract and tests so future agents can run one command.