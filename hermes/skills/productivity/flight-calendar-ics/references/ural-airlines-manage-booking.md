# Ural Airlines manage-booking to ICS notes

Use this when a user sends a Ural Airlines manage-booking link like `service.uralairlines.ru/?pnr=...&lastName=...` or a tracking redirect whose `u=` parameter points to that URL.

## Provenance

Derived from a live Ural Airlines manage-booking session in May 2026. Treat endpoint details as implementation notes that must be re-verified against the current frontend bundle before relying on them.

## Workflow

1. Decode redirect links first: extract the `u=` query parameter and URL-decode it. The useful values are normally `pnr` and `lastName`.
2. Use the one-command CLI whenever possible:
   `python scripts/flight_calendar_ics.py --json ural --url '<URL>' --output-json /private/dir/ural.input.json --output-ics /private/dir/ural.ics`.
3. The CLI fetches the SPA shell at `https://service.uralairlines.ru/`, discovers the current frontend version/assets, then fetches `/<version>/env/env.json` from the service host to get the current `API_URL` and frontend API key material. A private local `.env`/copied `env.json` is not required for normal use.
4. The useful API base observed was `https://u6ibe.book.uralairlines.ru/api/v2.3/`, but treat it as dynamic and prefer the live frontend config.
5. The SPA calls `POST Session` first, then `GET Reservation` with params:
   - `pnrNumber=<PNR>`
   - `lastName=<LASTNAME>`
   - header `X-Session: <sessionKey>` from `POST Session`
6. The frontend adds an `X-Api-Key` header via the obfuscated JS helper referenced from the shell. Reuse/execute the current frontend helper rather than hard-coding the generated value. Node.js is required by the CLI for this helper execution. Compute `timestampDiff` from `API_URL/settings/CurrentDateUtc`; if that endpoint fails, use numeric `0` to avoid an invalid `undefined`-interleaved header.
7. Reservation response fields useful for ICS:
   - `data.number` → PNR
   - `data.journey.outboundFlights[]`, `returnFlights[]`, `separateFlights[]`
   - per flight: `origin`, `destination`, `departureDate`, `departureDateUtc`, `arrivalDate`, `arrivalDateUtc`, `flightNumber`, `operatingCarrier`, `marketingCarrier`, `flightDuration`, `aircraft`, `statuses`, `referenceNumber`
   - `data.tickets[]` maps `flightReferences[]` to ticket numbers and passenger references
   - `data.passengers[]` contains surnames/names and contact/document data; do not leak these in chat/logs.
8. Airport timezone handling still matters. For the observed domestic route: `SVX=Asia/Yekaterinburg`, `DME=Europe/Moscow`. Verify any new airport code before generating ICS or rerun with `--tz CODE=Area/City`.
9. The `ural` command generates the standard itinerary JSON and `.ics` in one pass; both artifacts are owner-only (`0600`).

## Privacy

Do not print raw PNR, surname, passenger names, document numbers, phone/email, ticket numbers, full booking URLs, or generated API headers in chat. It is acceptable to include PNR/passenger/ticket/booking URL in the private `.ics` deliverable when needed for operational usefulness.

## Validation

Require the same skill quality bar as other carriers: JSON envelope `ok=true`, expected process steps, one VEVENT per segment, UTC `DTSTART`/`DTEND` ending in `Z`, no placeholders, local times preserved in descriptions, and owner-only mode for generated artifacts.
