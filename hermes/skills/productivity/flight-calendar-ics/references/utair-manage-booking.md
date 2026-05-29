# Utair Manage-Booking Workflow

Use this reference when adding or operating first-class Utair support in the `flight-calendar-ics` skill.

## Confirmed live flow

Utair's manage-booking page is a JavaScript SPA. The itinerary is not present in the initial HTML, so do not scrape the page body. Use the public frontend/API flow instead:

1. Obtain a public client-credentials token:
   - `POST https://b.utair.ru/oauth/token`
   - form fields: `client_id=website_client`, `grant_type=client_credentials`
   - browser-like headers are sufficient (`User-Agent`, `Origin: https://www.utair.ru`, `Referer`).
2. Query orders:
   - `GET https://b.utair.ru/api/v3/orders`
   - params: `filters[locator]=<PNR>`, `filters[passenger_lastname]=<LAST_NAME>`
   - authorization bearer header; do not record or print the bearer value.
   - browser-like `Origin`/`Referer` headers.
3. Convert returned `future[]` / `past[]` order data into the skill's standard itinerary JSON, then generate `.ics` through the single agent CLI.

## Agent command target

The intended first-class command is:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json utair \
  --url '<Utair order-manage URL>' \
  --output-json /private/dir/utair-trip.input.json \
  --output-ics /private/dir/utair-trip.ics
```

It should also support explicit credentials without a URL:

```bash
python <skill_dir>/scripts/flight_calendar_ics.py --json utair \
  --rloc '<PNR>' \
  --last-name '<SURNAME>' \
  --output-json /private/dir/utair-trip.input.json \
  --output-ics /private/dir/utair-trip.ics
```

The command should return the standard envelope `schema_version: flight-calendar-ics-cli.v1`, `ok`, `command: utair`, ordered `process`, and safe summary `data`.

Expected process trace:

`parse_args → parse_pnr_source → load_timezone_map → fetch_utair_token → fetch_utair_orders → convert_to_itinerary → build_calendar → validate_ics → write_json → write_ics/skipped → emit_json`

## Source parsing

Accept URLs like:

`https://www.utair.ru/order-manage?rloc=...&last_name=...`

Rules:

- Parse `rloc` and `last_name`; ignore `utm_*` parameters.
- Support URL-decoded Cyrillic surnames.
- Normalize locator to uppercase.
- Do not print the raw URL, locator, or surname in errors/stdout/stderr.
- If required fields are missing, return a redacted validation error.

## Response mapping notes

Observed safe structural fields in live data:

- top-level `future[]` orders exist for upcoming trips;
- `offers[]` contains `brand_code`, `brand_name`, and `segment_id`;
- `services[]` may be empty;
- `available_actions` is a dict.

Conversion should look for common segment/order fields defensively and fail loudly when required calendar fields are absent:

- flight number: carrier/airline code plus flight number, e.g. `UT` + `281`;
- route: departure and arrival airport codes;
- local times: departure/arrival local ISO fields;
- cities/terminals/status when present;
- passengers and tickets from passenger/ticket arrays when present;
- fare from `offers[].segment_id` matching a segment;
- baggage only when explicitly present. Do not infer baggage from fare brand.

## Timezone handling

Utair tickets print local times. Convert to UTC `DTSTART`/`DTEND` using per-airport IANA timezones. Known useful defaults from the investigated case:

- `SVX = Asia/Yekaterinburg`
- `KUF = Europe/Samara`
- Moscow airports (`SVO`, `DME`, `VKO`) and `LED = Europe/Moscow`

If an airport timezone is unknown, stop with a clear redacted error and support `--tz CODE=Area/City` overrides.

## Privacy and artifact rules

Sensitive values:

- full manage-booking URL;
- PNR/locator;
- passenger surname/name;
- ticket numbers;
- bearer tokens;
- credential-bearing query strings.

Rules:

- Never echo sensitive values in stdout/stderr/chat summaries.
- Redact `rloc=`, `last_name=`, `lastName=`, `filters[locator]`, `filters[passenger_lastname]`, URL-encoded variants, bearer authorization headers, and 13-digit ticket numbers.
- Write normalized JSON and `.ics` artifacts as owner-only `0600` in deliberate private directories.
- It is acceptable and useful for the private `.ics` itself to contain booking details needed for import/use.

## TDD integration checklist

Add or update tests before implementation:

- schema enum includes `utair`;
- `doctor` advertises `utair`;
- URL parser handles Cyrillic/URL-encoded `last_name` and redacts errors;
- fetch functions are tested with mocked HTTP, not live Utair calls;
- mocked order response converts to one or more standard itinerary segments;
- private JSON/ICS modes are `0600`;
- stdout/stderr envelope does not contain PNR, surname, passenger names, ticket numbers, bearer tokens, or full booking URLs;
- `.ics` has one `VEVENT` per segment, UTC timestamps ending `Z`, and no placeholders.

Contract test command:

```bash
cd <flight-calendar-ics skill directory>
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_flight_calendar_ics_cli
```
