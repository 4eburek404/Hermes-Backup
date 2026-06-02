# CLI Contract

This file owns the agent-facing command contract for `flight-calendar-ics`. It describes how agents use the single CLI and how the emitted JSON envelope is validated. It does not own carrier API details, manual PDF extraction, timezone catalog generation, event wording, or source/runtime sync.

## Entrypoint

Use the single Python executable as the agent-facing entrypoint:

```bash
cd "$SKILL_DIR"
python scripts/flight_calendar_ics.py --json doctor
python scripts/flight_calendar_ics.py --json validate --input /path/to/itinerary.json
python scripts/flight_calendar_ics.py --json make --input /path/to/itinerary.json --output /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json aeroflot --url '<Aeroflot PNR URL>' --output-json /private/dir/trip.input.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json ural --url '<Ural Airlines manage-booking URL or tracker redirect>' --output-json /private/dir/trip.input.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json utair --url '<Utair order-manage URL>' --output-json /private/dir/trip.input.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json redwings --url '<Red Wings /find/<PNR>/<ACCESS_KEY>/Submit URL>' --output-json /private/dir/trip.input.json --output-ics /private/dir/flights.ics
```

Legacy helper scripts remain implementation modules and compatibility tools; agents should prefer the single CLI and parse its JSON envelope, not scrape helper stdout.

## `doctor` as runbook source

`doctor` is the source of truth for the short agent workflow. It emits `data.agent_contract` so `../../SKILL.md` can remain compact.

Normal steps:

1. `collect_source` — use explicit evidence or already-supplied attachments/cache; do not ask again for retrievable ticket data.
2. `run_one_command` — create a private output directory and run exactly one `--json` command from `dispatch_matrix`.
3. `verify` — parse the envelope and verify the generated `.ics` before delivery.
4. `deliver` — send `MEDIA:/absolute/path/flights.ics` with a safe chat summary.

`data.agent_contract.dispatch_matrix` contains argv templates for:

- `make` — existing canonical itinerary JSON or manually normalized PDF/email/screenshot data;
- `aeroflot` — Aeroflot direct booking URL, or PNR + surname with optional `--first-name` for ambiguous surname lookup;
- `ural` — Ural Airlines manage-booking URL or tracker redirect;
- `utair` — Utair order-manage URL;
- `redwings` — Red Wings/Websky direct `#/find/<PNR>/<ACCESS_KEY>/Submit` link.

The matrix uses placeholders only. It must never contain real PNRs, names, `pnr_key` values, access keys, bearer tokens, ticket numbers, or full personal booking URLs.

If a future command can deterministically classify and dispatch sources by itself, add it to the CLI and expose it in `doctor` before adding prose to `../../SKILL.md`.

## JSON envelope v1

Schema files:

- `schemas/cli-envelope.v1.schema.json` — response envelope emitted by `--json`.
- `schemas/itinerary.v1.schema.json` — provider-agnostic canonical itinerary input consumed before ICS generation.

Required top-level shape:

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
- `process` is ordered and describes actual internal stages attempted by the CLI.
- With `--json`, usage/argparse errors must also return this envelope with `ok=false` and `error.code=usage_error`.
- stdout/stderr must not include PNR keys, access keys, passenger names, ticket numbers, bearer tokens, or full booking URLs. Segment count, route, flight number, UTC/local times, and artifact paths are acceptable.

## Process ownership

- `doctor`: expose entrypoint, commands, JSON contract, input contract, `agent_contract`, and sensitive stdout policy without touching user data.
- `validate`: load canonical itinerary JSON, validate schema and semantics, build/validate calendar in memory, write nothing, emit safe segment summary.
- `make`: validate canonical itinerary JSON and write a private `.ics` file.
- carrier commands: parse source, load timezone map, fetch/read carrier data, convert to canonical itinerary JSON, validate, build calendar, write private JSON/ICS artifacts, emit safe summary.

Carrier-specific runtime details live in the airline owner files under `../carriers/`, not in this file.

## Verification gates

Before delivering a generated calendar:

1. Envelope has `schema_version == "flight-calendar-ics-cli.v1"`.
2. `ok == true`.
3. `command` matches the selected source route.
4. `data.segments_count >= 1`.
5. `.ics` path exists.
6. Private artifact mode is `0600` where applicable.
7. `.ics` contains `BEGIN:VCALENDAR`.
8. `BEGIN:VEVENT` count equals `segments_count`.
9. All `DTSTART`/`DTEND` values are UTC timestamps ending in `Z`.
10. No placeholders such as `TBD`, `UNKNOWN`, `None`, or `null` appear in the final `.ics`.
11. For carrier commands, `load_timezone_map` proves the bundled Travelpayouts asset loaded and no local default map was used.
12. Final chat summary excludes PNR keys, access keys, passenger names, ticket numbers, bearer tokens, fare/payment details, and full booking URLs.

## Test contract

Run from the skill root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_flight_calendar_ics_cli
```

The tests should assert:

- the single executable exists and emits the JSON envelope;
- `doctor` describes commands, entrypoint, and `data.agent_contract`;
- actual `doctor`/happy-path/error envelopes validate against `schemas/cli-envelope.v1.schema.json`;
- `validate` is check-only and machine-readable;
- `make` writes `.ics` with mode `0600`;
- each carrier command writes private artifacts with mode `0600` and keeps carrier-specific private values out of stdout/stderr;
- invalid alarms and usage errors return JSON errors, not tracebacks or raw argparse text;
- compatibility helper surfaces remain tested when they can write private artifacts.
