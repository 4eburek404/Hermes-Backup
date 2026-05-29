# Ural Airlines live frontend flow for calendar generation

## When this applies

Use this when creating an `.ics` file from a Ural Airlines manage-booking URL, including tracker-wrapped links where the real URL is in a `u=` or `url=` query parameter.

## Durable learning

For Ural Airlines, a future agent should not manually depend on a private local `.env` or copied `env.json` for each booking. The safer one-command flow is to use the current public frontend state from `https://service.uralairlines.ru/` at runtime:

1. Parse `pnr` and `lastName` from the direct URL or from a tracker redirect parameter (`u=` / `url=`).
2. Fetch the live manage-booking shell HTML.
3. Discover the current frontend version and asset paths from the HTML.
4. Fetch the live frontend `/<version>/env/env.json` from the site, not from a local private file.
5. Fetch server time from `API_URL/settings/CurrentDateUtc` and compute `timestampDiff`; if that endpoint fails, use numeric `0` rather than allowing an `undefined` value into the header generator.
6. Read the app bundle to identify the obfuscated API-key helper function names currently invoked by the axios interceptor.
7. Run the current helper JavaScript in a sandboxed Node.js VM to produce `X-Api-Key`; validate that the header is non-empty and does not contain `undefined`.
8. POST `Session` with `X-Api-Key`; use returned `sessionKey` as `X-Session`.
9. GET `Reservation?pnrNumber=...&lastName=...`.
10. Convert the reservation JSON to the standard itinerary JSON, then generate `.ics` from that JSON.
11. Write both JSON and `.ics` as owner-only files (`0600`).

## Safety and output policy

- Do not print or persist raw `API_KEY`, generated `X-Api-Key`, `sessionKey`, PNR, passenger names, ticket numbers, document numbers, phone/email, or full booking URLs in stdout/stderr/process summaries.
- Store the intermediate standard itinerary JSON for reproducibility, but as `0600` because it contains booking and passenger details.
- JSON envelopes should expose only route/flight/time summaries and artifact paths.
- Redaction must cover Ural query parameters: `pnr=`, `pnrNumber=`, and `lastName=` in addition to existing Aeroflot `pnrKey`/`pnrLocator` and ticket-number patterns.

## Testing pattern

Add contract tests before implementation:

- `doctor` and the JSON schema list command `ural`.
- URL parser decodes tracker-wrapped Ural URLs without requiring local `.env`.
- CLI command writes both JSON and `.ics` with `0600` and redacted process/data summaries.
- Redactor masks Ural booking URL query credentials.

When importing modules in tests with `importlib.util.module_from_spec(...); spec.loader.exec_module(module)`, avoid `@dataclass` at module import time unless the test registers the module in `sys.modules` first. `typing.NamedTuple` avoids that importlib/dataclasses edge case for small immutable records.

## One-command shape

```bash
python3 scripts/flight_calendar_ics.py --json ural \
  --url 'https://service.uralairlines.ru/?pnr=...&lastName=...' \
  --output-json /private/path/ural.json \
  --output-ics /private/path/ural.ics
```

Optional flags:

- `--pnr` and `--last-name` instead of `--url`.
- `--tz CODE=Area/City` for airports not in the built-in map.
- `--frontend-base` only for diagnostics/tests, not normal use.
