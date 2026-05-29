# Agent CLI contract for flight-calendar-ics

This reference defines the machine-readable contract future agents should use when producing or validating flight calendar files.

## Entrypoint

Use the single Python executable as the agent-facing entrypoint:

```bash
cd <skill_dir>
python scripts/flight_calendar_ics.py --json doctor
python scripts/flight_calendar_ics.py --json validate --input /path/to/itinerary.json
python scripts/flight_calendar_ics.py --json make --input /path/to/itinerary.json --output /private/dir/trip.ics
python scripts/flight_calendar_ics.py --json aeroflot --url '<Aeroflot PNR URL>' --output-json /private/dir/trip.input.json --output-ics /private/dir/trip.ics
python scripts/flight_calendar_ics.py --json ural --url '<Ural Airlines manage-booking URL or tracker redirect>' --output-json /private/dir/trip.input.json --output-ics /private/dir/trip.ics
python scripts/flight_calendar_ics.py --json utair --url '<Utair order-manage URL>' --output-json /private/dir/trip.input.json --output-ics /private/dir/trip.ics
```

Legacy helper scripts remain implementation modules and compatibility tools:

- `scripts/make_flight_ics.py`
- `scripts/aeroflot_pnr_to_itinerary.py`
- `scripts/ural_airlines_to_itinerary.py`
- `scripts/utair_to_itinerary.py`

Agents should not scrape their human stdout when the single CLI can be used. Use `--json` and parse the envelope.

## JSON envelope v1

Schema files:

- `schemas/cli-envelope.v1.schema.json` — response envelope emitted by `--json`.
- `schemas/itinerary.v1.schema.json` — provider-agnostic canonical itinerary input consumed before ICS generation.

Required top-level fields:

```json
{
  "schema_version": "flight-calendar-ics-cli.v1",
  "ok": true,
  "command": "make",
  "process": [
    {"step": "parse_args", "status": "ok"}
  ],
  "data": {}
}
```

Error shape:

```json
{
  "schema_version": "flight-calendar-ics-cli.v1",
  "ok": false,
  "command": "validate",
  "process": [
    {"step": "parse_args", "status": "ok"},
    {"step": "error", "status": "error"},
    {"step": "emit_json", "status": "ok"}
  ],
  "error": {
    "code": "validation_error",
    "message": "invalid alarm minutes value at alarms_minutes[1]: 'abc'; use positive integers"
  }
}
```

Contract rules:

- `schema_version` is stable for this envelope: `flight-calendar-ics-cli.v1`.
- `ok=true` means `data` is present and `error` is absent.
- `ok=false` means `error.code` and `error.message` are present and `data` is absent.
- `process` is ordered and describes the actual internal stages the CLI attempted.
- stdout/stderr must not include PNR keys, passenger names, ticket numbers, or full booking URLs. Route, flight number, UTC times, segment count, and artifact paths are acceptable.
- For Ural Airlines, normal use must not depend on a private local `.env` or copied `env.json`; the command fetches the carrier's current public frontend config and derives request headers at runtime.
- For Utair, normal use obtains a public `client_credentials` token at runtime and then looks up orders through `GET /api/v3/orders`; bearer tokens, locators, surnames, passenger names, full booking URLs, and ticket numbers must not be printed.
- With `--json`, usage/argparse errors must also return this envelope with `ok=false` and `error.code=usage_error`; do not make agents scrape argparse human text.

## Internal CLI process

### `doctor`

Purpose: expose the contract and available commands without touching itinerary data.

Process:

1. `parse_args`
2. `load_input` with `status=skipped`
3. `emit_json`

Expected data includes:

- `entrypoint`
- `entrypoint_kind: single-python-executable`
- `commands`
- `json_contract`
- `sensitive_stdout_policy`

### `validate`

Purpose: validate itinerary JSON and produce a parseable summary without writing files.

Process:

1. `parse_args`
2. `load_input`
3. `validate_itinerary_schema`
4. `validate_itinerary_semantics`
5. `build_calendar`
6. `validate_ics`
7. `no_write`
8. `emit_json`

Expected data includes:

- `segments_count`
- `segments[]` with `flight_number`, `route`, `dtstart_utc`, `dtend_utc`
- `write_performed: false`

### `make`

Purpose: validate itinerary JSON and write an importable `.ics` file.

Process:

1. `parse_args`
2. `load_input`
3. `validate_itinerary_schema`
4. `validate_itinerary_semantics`
5. `build_calendar`
6. `validate_ics`
7. `write_output`
8. `emit_json`

Safety contract:

- `.ics` is written with mode `0600`.
- Missing output directories are created before writing.
- JSON stdout contains segment summaries and the output path, not PNR/passenger/ticket values.

### `aeroflot`

Purpose: fetch Aeroflot PNR data, convert it to the standard itinerary JSON, validate generated calendar data, and optionally write `.ics`.

Process:

1. `parse_args`
2. `parse_pnr_source`
3. `load_timezone_map`
4. `fetch_aeroflot_pnr`
5. `convert_to_itinerary`
6. `validate_itinerary_schema`
7. `validate_itinerary_semantics`
8. `build_calendar`
9. `validate_ics`
10. `write_json`
11. `write_ics` or skipped `write_ics`
12. `emit_json`

Safety contract:

- The CLI may write private booking data into the requested JSON/ICS artifacts because those artifacts are the intended deliverable.
- JSON/ICS artifacts are written with mode `0600`.
- The compatibility helpers `scripts/make_flight_ics.py` and `scripts/aeroflot_pnr_to_itinerary.py` must also write private artifacts with mode `0600` when invoked directly.
- The machine-readable stdout summary remains redacted and operational: segment count, routes, and artifact paths only.

### `ural`

Purpose: fetch Ural Airlines Reservation data from a manage-booking URL or tracker redirect, convert it to the standard itinerary JSON, validate generated calendar data, and optionally write `.ics`.

Process:

1. `parse_args`
2. `parse_pnr_source`
3. `load_timezone_map`
4. `fetch_ural_reservation`
5. `convert_to_itinerary`
6. `validate_itinerary_schema`
7. `validate_itinerary_semantics`
8. `build_calendar`
9. `validate_ics`
10. `write_json`
11. `write_ics` or skipped `write_ics`
12. `emit_json`

Safety/runtime contract:

- The CLI decodes direct Ural URLs and tracker redirects whose `u=`/`url=` query parameter points to `service.uralairlines.ru`.
- The command fetches the current Ural frontend shell, config, and helper bundle at runtime; it does not require agents to open or maintain a local `.env`/copied `env.json` for normal use.
- Node.js is required to execute the current frontend helper that generates `X-Api-Key`; generated headers and `sessionKey` must never be printed.
- JSON/ICS artifacts are written with mode `0600`.
- The machine-readable stdout summary remains redacted and operational: segment count, routes, and artifact paths only.

### `utair`

Purpose: fetch Utair order data from an `order-manage` URL or explicit `--rloc`/`--last-name`, convert it to the standard itinerary JSON, validate generated calendar data, and optionally write `.ics`.

Process:

1. `parse_args`
2. `parse_pnr_source`
3. `load_timezone_map`
4. `fetch_utair_token`
5. `fetch_utair_orders`
6. `convert_to_itinerary`
7. `validate_itinerary_schema`
8. `validate_itinerary_semantics`
9. `build_calendar`
10. `validate_ics`
11. `write_json`
12. `write_ics` or skipped `write_ics`
13. `emit_json`

Safety/runtime contract:

- The CLI parses `rloc` and `last_name` from `www.utair.ru/order-manage` URLs; tracking/marketing query parameters are ignored.
- The command fetches a short-lived public OAuth token (`client_id=website_client`, `grant_type=client_credentials`) at runtime; the bearer token must never be printed.
- The command queries `https://b.utair.ru/api/v3/orders` with `filters[locator]` and `filters[passenger_lastname]`, then maps `future[]`/`past[]` order segments into standard itinerary JSON.
- JSON/ICS artifacts are written with mode `0600`.
- The machine-readable stdout summary remains redacted and operational: segment count, routes, local times, and artifact paths only.

## Test contract

Run the contract tests from the skill root:

```bash
cd <skill_dir>
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_flight_calendar_ics_cli
```

The tests assert:

- the single executable exists and emits the JSON envelope;
- `doctor` describes the commands and entrypoint;
- `validate` is check-only and machine-readable;
- the canonical itinerary schema exists, is Draft 2020-12 valid, provider-agnostic, and validates `templates/aeroflot-itinerary.example.json`;
- `validate` rejects unknown canonical fields and missing endpoint timezone at `validate_itinerary_schema` before `build_calendar`;
- `make` writes an `.ics` file with mode `0600`;
- `ural` decodes direct/tracker URLs, writes private JSON/ICS artifacts with mode `0600`, and keeps PNR/surname/ticket details out of stdout/stderr;
- `utair` parses manage-booking URLs with Cyrillic surnames, writes private JSON/ICS artifacts with mode `0600`, and keeps locator/surname/passenger/ticket/token details out of stdout/stderr;
- invalid alarms return a JSON `validation_error`, not a traceback;
- stdout/stderr do not echo representative private values from the fixture.
