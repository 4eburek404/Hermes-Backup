# Ural Airlines

Use this file when creating `.ics` from Ural Airlines manage-booking links or when maintaining the Ural adapter. This file owns Ural-specific URL parsing, live frontend config discovery, API-key helper execution, session/reservation flow, and response mapping.

## Scope

Applicable sources:

- direct manage-booking URL like `https://service.uralairlines.ru/?pnr=<PNR>&lastName=<LASTNAME>`;
- tracker-wrapped links whose `u=` or `url=` parameter points to the service URL;
- Ural ticket/PDF/email/screenshot where manual canonical normalization is more appropriate than live lookup.

Endpoint details are implementation notes that must be re-verified against the current frontend bundle when the flow breaks.

## Accepted source evidence

1. Decode redirect links first: extract and URL-decode `u=` / `url=` query parameters.
2. Parse useful values from direct or decoded service URL:
   - `pnr`;
   - `lastName`.
3. Optional flags may provide `--pnr` and `--last-name` instead of `--url`.

Do not print the raw URL, PNR, or surname in errors/stdout/stderr.

## Live frontend/API flow

Do not depend on a private local `.env` or copied `env.json` for each booking. The normal one-command flow uses current public frontend state from `https://service.uralairlines.ru/` at runtime:

1. Parse `pnr` and `lastName` from direct URL or tracker redirect.
2. Fetch live manage-booking shell HTML.
3. Discover current frontend version and asset paths from HTML.
4. Fetch live frontend `/<version>/env/env.json` from the site to get current `API_URL` and frontend API-key material.
5. Fetch server time from `API_URL/settings/CurrentDateUtc` and compute `timestampDiff`; if that endpoint fails, use numeric `0` rather than allowing `undefined` into the header generator.
6. Read the app bundle to identify the obfuscated API-key helper function names invoked by the axios interceptor.
7. Run current helper JavaScript in a sandboxed Node.js VM to produce `X-Api-Key`; validate header is non-empty and does not contain `undefined`.
8. POST `Session` with `X-Api-Key`; use returned `sessionKey` as `X-Session`.
9. GET `Reservation?pnrNumber=<PNR>&lastName=<LASTNAME>` with `X-Session`.
10. Convert reservation JSON to canonical itinerary JSON, then generate `.ics`.
11. Write JSON and `.ics` as owner-only files (`0600`).

Observed API base included `https://u6ibe.book.uralairlines.ru/api/v2.3/`, but treat it as dynamic and prefer live frontend config.

Node.js is required by the CLI for frontend helper execution.

## Response → canonical itinerary mapping

Useful reservation fields:

- `data.number` → PNR;
- `data.journey.outboundFlights[]`, `returnFlights[]`, `separateFlights[]`;
- per flight: `origin`, `destination`, `departureDate`, `departureDateUtc`, `arrivalDate`, `arrivalDateUtc`, `flightNumber`, `operatingCarrier`, `marketingCarrier`, `flightDuration`, `aircraft`, `statuses`, `referenceNumber`;
- `data.tickets[]` maps `flightReferences[]` to ticket numbers and passenger references;
- `data.passengers[]` contains surnames/names and contact/document data; do not leak these in chat/logs.

Airport timezone handling still matters. For any unknown airport, use the bundled catalog or explicit `--tz CODE=Area/City`; do not maintain Ural-local timezone maps.

## CLI command shape

Prefer exact argv from `doctor.data.agent_contract.dispatch_matrix`. Normal shape:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json ural \
  --url '<https://service.uralairlines.ru/?pnr=<PNR>&lastName=<LASTNAME>>' \
  --output-json /private/dir/ural.input.json \
  --output-ics /private/dir/flights.ics
```

Optional flags:

- `--pnr` and `--last-name` instead of `--url`.
- `--tz CODE=Area/City` for airports not in the built-in map.
- `--frontend-base` only for diagnostics/tests, not normal use.

## Privacy

Do not print or persist raw values in chat/log summaries for:

- PNR or locator;
- last name / passenger names;
- full manage-booking URL or tracking redirect;
- generated `X-Api-Key`, frontend API key material, session keys, API headers;
- document/contact/ticket/fare/payment data;
- raw reservation payloads.

The private `.ics` may include operational booking details when useful after import. Chat summaries should use counts, routes, and non-sensitive timing only.

Redaction must cover Ural query parameters: `pnr=`, `pnrNumber=`, and `lastName=`.

## Carrier-specific pitfalls

- Do not manually depend on private local `.env` or copied `env.json`; those are debug artifacts, not the normal path.
- Do not hard-code obfuscated API-key values; execute the current frontend helper in isolation.
- Do not allow `undefined` into the generated API key; use numeric `0` timestamp diff when server-time endpoint fails.
- Do not treat initial HTML as itinerary data; it is a shell.
- Avoid `@dataclass` at module import time in tests that load modules with `importlib.util.module_from_spec(...); spec.loader.exec_module(module)` unless the module is registered in `sys.modules` first. `typing.NamedTuple` avoids that edge case for small immutable records.

## Verification

- `doctor` and schema list command `ural`.
- URL parser decodes direct and tracker-wrapped Ural URLs without requiring local env files.
- CLI fetches live frontend config and does not require copied `.env`/`env.json` in normal path.
- Generated `X-Api-Key` is non-empty and redacted.
- JSON and `.ics` artifacts are mode `0600`.
- Envelope exposes only route/flight/time summaries and artifact paths.
- `.ics` has one `VEVENT` per segment, UTC timestamps ending `Z`, no placeholders, and local times preserved in descriptions.
- Final report can explicitly say no local `.env` / copied `env.json` was required for normal path.
