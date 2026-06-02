# Aeroflot PNR + surname deep-link generation

Use this reference when an Aeroflot ticket/PDF/email gives a booking locator (PNR) and passenger surname but not an existing `pnrKey`/`pnr_key` deep link. The goal is to generate a direct manage-booking URL for the imported calendar event programmatically, without browser automation.

## Evidence from Aeroflot SPA

The Aeroflot manage-booking SPA at:

```text
https://www.aeroflot.ru/sb/pnr/app/ru-ru#/search
```

loads current settings from inline `window.initial.urls`. For the observed build, both name search and key search use:

```text
/se/api/app/pnr/view/v3
```

The submit flow has two modes:

- `type_query=name`: payload contains `pnr_locator`, `last_name`, `first_name`, `lang`, `country`;
- `type_query=key`: payload contains `pnr_locator`, `pnr_key`, `lang`, `country`.

After a successful name search, the API response data contains `pnr_key` and `pnr_locator`. The SPA then builds the booking route query and navigates to:

```text
#/pnr?pnr_key=<pnr_key>&pnr_locator=<pnr_locator>
```

So the direct booking URL is:

```text
https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?pnr_key=<urlencoded pnr_key>&pnr_locator=<urlencoded pnr_locator>
```

## Programmatic algorithm

1. Extract from the source document:
   - booking locator / PNR;
   - passenger surname;
   - passenger first name if available (fallback for ambiguous PNRs).
2. POST to the Aeroflot PNR endpoint:

```http
POST https://www.aeroflot.ru/se/api/app/pnr/view/v3
Content-Type: application/json
Accept: application/json
Origin: https://www.aeroflot.ru
Referer: https://www.aeroflot.ru/sb/pnr/app/ru-ru#/search
X-App-Identity: 0
```

Surname-only payload:

```json
{
  "pnr_locator": "<PNR>",
  "last_name": "<SURNAME>",
  "first_name": "",
  "lang": "ru",
  "country": "ru"
}
```

If the response reports `SabrePNRAmbiguousException` or `PassengerAmbiguous`, retry once with `first_name` populated.

3. Require a JSON response with `success: true` and `data.pnr_key` + `data.pnr_locator`.
4. Build the URL:

```python
from urllib.parse import urlencode
url = "https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?" + urlencode({
    "pnr_key": data["pnr_key"],
    "pnr_locator": data["pnr_locator"],
})
```

5. Verify the URL without browser automation by replaying key mode:

```json
{
  "pnr_locator": "<PNR>",
  "pnr_key": "<pnr_key>",
  "lang": "ru",
  "country": "ru"
}
```

The verification response must have `success: true` and booking data for the same locator.

## Privacy and output rules

- Treat generated `pnr_key` as a booking credential.
- Do not print full generated URLs, `pnr_key`, PNR, passenger names, ticket numbers, or API response bodies in chat/log summaries.
- It is acceptable to write the generated URL into private `.ics` artifacts requested by the user, because that is the intended import payload.
- Artifact files containing the URL should be mode `0600`.
