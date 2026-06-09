# Aeroflot

Use this file when creating `.ics` from Aeroflot booking evidence or when maintaining the Aeroflot adapter. This file owns Aeroflot-specific PNR/name lookup and direct manage-booking deep-link generation.

## Scope

Applicable sources:

- Aeroflot PNR/search URL;
- ticket/PDF/email with booking locator and passenger surname;
- booking evidence where the user wants a direct link back to the Aeroflot booking.

If the source is only manual flight facts and no direct booking link is needed, normalize to canonical itinerary JSON and use `make`.

## Accepted source evidence

Extract only what is needed:

- booking locator / PNR;
- passenger surname;
- passenger first name if available, used as fallback for ambiguous surname lookup;
- visible flight segment facts for calendar generation.

Do not ask the user again for PNR/surname if they already supplied a PDF/email/screenshot and the values can be extracted from the cached source.

## Live/API flow

Aeroflot manage booking SPA:

```text
https://www.aeroflot.ru/sb/pnr/app/ru-ru#/search
```

The SPA loads settings from inline `window.initial.urls`. The observed name and key search endpoint is:

```text
/se/api/app/pnr/view/v3
```

Submit modes:

- `type_query=name`: payload contains `pnr_locator`, `last_name`, `first_name`, `lang`, `country`.
- `type_query=key`: payload contains `pnr_locator`, `pnr_key`, `lang`, `country`.

After successful name search, response data contains `pnr_key` and `pnr_locator`. The SPA navigates to:

```text
private deep-link fragment with redacted key and locator parameters
```

The direct booking URL is:

```text
private generated booking deep-link with redacted query parameters
```

## Programmatic algorithm

1. Extract PNR, surname, and first name if available.
2. POST to the PNR endpoint with browser-like JSON headers:

```http
POST https://www.aeroflot.ru/se/api/app/pnr/view/v3
Content-Type: application/json
Accept: application/json
Origin: https://www.aeroflot.ru
Referer: https://www.aeroflot.ru/sb/pnr/app/ru-ru#/search
X-App-Identity: 0
```

Surname-only payload shape:

```json
{
  "pnr_locator": "<PNR>",
  "last_name": "<SURNAME>",
  "first_name": "",
  "lang": "ru",
  "country": "ru"
}
```

3. If the response reports `SabrePNRAmbiguousException` or `PassengerAmbiguous`, retry once with `first_name` populated.
4. Require JSON response with `success: true` and `data.pnr_key` plus `data.pnr_locator`.
5. Build the direct URL using URL-encoded `pnr_key` and `pnr_locator`.
6. Verify without browser automation by replaying key mode:

```json
{
  "pnr_locator": "<PNR>",
  "pnr_key": "<pnr_key>",
  "lang": "ru",
  "country": "ru"
}
```

The verification response must have `success: true` and booking data for the same locator.

## Response → canonical itinerary mapping

The adapter should map Aeroflot booking segments into canonical itinerary JSON before ICS generation:

- carrier: `Aeroflot` / `SU` as available;
- flight number;
- departure/arrival airport IATA codes;
- local departure/arrival datetimes;
- per-airport IANA timezones from the bundled catalog or explicit `--tz`;
- passenger/ticket/aircraft/status/booking link only when present and useful inside the private artifact.

Carrier raw fields remain in the adapter/private layer; do not extend canonical schema with Aeroflot-specific raw API fields.

## CLI command shape

Prefer `doctor.data.agent_contract.dispatch_matrix` for exact argv templates. Normal shape:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json aeroflot \
  --url '<Aeroflot source URL or direct PNR URL>' \
  --output-json /private/dir/aeroflot.input.json \
  --output-ics /private/dir/flights.ics
```

If the command supports explicit PNR fields, use placeholders only:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json aeroflot \
  --pnr '<PNR>' \
  --last-name '<SURNAME>' \
  --first-name '<FIRST_NAME_IF_NEEDED>' \
  --output-json /private/dir/aeroflot.input.json \
  --output-ics /private/dir/flights.ics
```

## Privacy

Treat generated `pnr_key` as a booking credential.

Do not print full generated URLs, `pnr_key`, PNR, passenger names, ticket numbers, document/contact/payment data, or API response bodies in chat/log summaries.

It is acceptable to write the generated URL into private `.ics` artifacts requested by the user, because that is the intended import payload. Artifact files containing the URL must be mode `0600`.

## Carrier-specific pitfalls

- A generic `#/search` URL is not a direct booking link. Direct links require `pnr_key`.
- Do not use browser automation when the API can obtain `pnr_key` programmatically.
- Do not stop after surname lookup if the API reports passenger ambiguity and first name is available.
- Do not expose generated `pnr_key` or direct URL in summaries; deliver it only inside the private `.ics` when requested.
- If PDF layout is ambiguous, use `core/source-normalization.md` before deciding segment times are missing.

## Verification

- Name/key API replay succeeds for the same locator.
- Adapter output validates as canonical itinerary JSON.
- `.ics` has one `VEVENT` per segment, UTC `DTSTART`/`DTEND`, no placeholders, mode `0600`.
- CLI envelope is `ok=true` and redacted.
- Final Telegram response sends `MEDIA:/.../flights.ics` and does not reveal PNR, passenger name, `pnr_key`, ticket/document/contact data, or the full direct URL.
