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
```

Legacy helper scripts remain implementation modules and compatibility tools:

- `scripts/make_flight_ics.py`
- `scripts/aeroflot_pnr_to_itinerary.py`

Agents should not scrape their human stdout when the single CLI can be used. Use `--json` and parse the envelope.

## JSON envelope v1

Schema file: `schemas/cli-envelope.v1.schema.json`.

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
3. `build_calendar`
4. `validate_ics`
5. `no_write`
6. `emit_json`

Expected data includes:

- `segments_count`
- `segments[]` with `flight_number`, `route`, `dtstart_utc`, `dtend_utc`
- `write_performed: false`

### `make`

Purpose: validate itinerary JSON and write an importable `.ics` file.

Process:

1. `parse_args`
2. `load_input`
3. `build_calendar`
4. `validate_ics`
5. `write_output`
6. `emit_json`

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
6. `build_calendar`
7. `validate_ics`
8. `write_json`
9. `write_ics` or skipped `write_ics`
10. `emit_json`

Safety contract:

- The CLI may write private booking data into the requested JSON/ICS artifacts because those artifacts are the intended deliverable.
- JSON/ICS artifacts are written with mode `0600`.
- The compatibility helpers `scripts/make_flight_ics.py` and `scripts/aeroflot_pnr_to_itinerary.py` must also write private artifacts with mode `0600` when invoked directly.
- The machine-readable stdout summary remains redacted and operational: segment count, routes, and artifact paths only.

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
- `make` writes an `.ics` file with mode `0600`;
- invalid alarms return a JSON `validation_error`, not a traceback;
- stdout/stderr do not echo representative private values from the fixture.
