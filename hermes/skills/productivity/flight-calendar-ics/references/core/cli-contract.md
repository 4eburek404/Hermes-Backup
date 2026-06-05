# CLI Contract

This file owns the agent-facing command contract for `flight-calendar-ics`: the single CLI entrypoint, `doctor.data.agent_contract`, JSON envelope, process traces, and contract tests. Carrier API details, manual extraction, timezone catalog generation, event wording, and source/runtime sync live in their own owner files.

## Entrypoint

Use the single Python executable as the agent-facing entrypoint:

```bash
cd "$SKILL_DIR"
python scripts/flight_calendar_ics.py --json doctor
python scripts/flight_calendar_ics.py --json validate --input /path/to/itinerary.json
python scripts/flight_calendar_ics.py --json build make --input /path/to/itinerary.json
python scripts/flight_calendar_ics.py --json build aeroflot --url-file /private/source-url.txt
python scripts/flight_calendar_ics.py --json build ural --url-file /private/source-url.txt
python scripts/flight_calendar_ics.py --json build utair --url-file /private/source-url.txt
python scripts/flight_calendar_ics.py --json build redwings --url-file /private/source-url.txt
```

The direct commands remain compatibility/diagnostic surfaces and stay tested:

```bash
python scripts/flight_calendar_ics.py --json make --input /path/to/itinerary.json --output /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json aeroflot --url '<Aeroflot PNR URL>' --output-json /private/dir/itinerary.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json ural --url '<Ural manage URL>' --output-json /private/dir/itinerary.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json utair --url '<Utair order-manage URL>' --output-json /private/dir/itinerary.json --output-ics /private/dir/flights.ics
python scripts/flight_calendar_ics.py --json redwings --url '<Red Wings find URL>' --output-json /private/dir/itinerary.json --output-ics /private/dir/flights.ics
```

Agents should prefer `build`: it owns the private output bundle and returns a safe machine-readable envelope.

## `doctor` as runbook source

`doctor` is the source of truth for the short agent workflow. It emits `data.agent_contract` so `../../SKILL.md` can remain compact.

Normal steps:

1. `collect_source` — use explicit evidence or already-supplied attachments/cache; do not ask again for retrievable ticket data.
2. `run_one_command` — run exactly one `--json build <route>` command from `dispatch_matrix`. The CLI creates the private bundle, chooses canonical artifact names, writes the generated artifacts, saves `envelope.json`, and verifies the bundle.
3. `verify` — parse stdout or `data.envelope_path`; require `schema_version`, `ok=true`, `data.segments_count>=1`, `data.ics_path`, and `data.verification.ok=true`.
4. `deliver` — send `MEDIA:/absolute/path/flights.ics` with a safe chat summary.

`data.agent_contract.dispatch_matrix` contains `command=build`, a `route`, and argv templates for:

- `make` — existing canonical itinerary JSON or manually normalized PDF/email/screenshot data;
- `aeroflot` — Aeroflot direct booking URL file, or PNR + surname with optional `--first-name` for ambiguous surname lookup;
- `ural` — Ural Airlines manage-booking URL/tracker redirect file;
- `utair` — Utair order-manage URL file;
- `redwings` — Red Wings/Websky direct `#/find/<PNR>/<ACCESS_KEY>/Submit` URL file.

The matrix uses placeholders only. It must never contain real PNRs, names, `pnr_key` values, access keys, bearer tokens, ticket numbers, or full personal booking URLs.

## Output bundle

`build` returns `ok=true` only after creating and verifying:

```text
<run-dir>/
  itinerary.json   0600
  flights.ics      0600
  envelope.json    0600
```

If `--output-dir` is omitted, the CLI creates a private `/tmp/flight-ics.*` directory and reports it as `data.output_dir`. `--output-dir` is for tests, reproducible diagnostics, cron artifacts, or explicit user-selected destinations.

`--url-file` is the preferred private input shape for carrier booking links. Raw `--url` remains available for compatibility, but agent-facing templates should prefer files for credential-bearing links.

## JSON envelope v1

Schema files:

- `schemas/cli-envelope.v1.schema.json` — response envelope emitted by `--json`.
- `schemas/itinerary.v1.schema.json` — provider-agnostic canonical itinerary input consumed before ICS generation.

Build success shape:

```json
{
  "schema_version": "flight-calendar-ics-cli.v1",
  "ok": true,
  "command": "build",
  "process": [
    {"step": "parse_args", "status": "ok"},
    {"step": "create_output_bundle", "status": "ok"},
    {"step": "verify_bundle", "status": "ok", "segments_count": 2},
    {"step": "write_envelope", "status": "ok", "artifact": "envelope", "mode": "0600"},
    {"step": "emit_json", "status": "ok"}
  ],
  "data": {
    "route": "make",
    "segments_count": 2,
    "json_path": "/tmp/flight-ics.x/itinerary.json",
    "ics_path": "/tmp/flight-ics.x/flights.ics",
    "envelope_path": "/tmp/flight-ics.x/envelope.json",
    "output_dir": "/tmp/flight-ics.x",
    "verification": {"ok": true, "event_count": 2}
  }
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
- `make`: validate canonical itinerary JSON and write a private `.ics` file for compatibility.
- `build`: create the private bundle, route to `make` or a carrier, write canonical artifacts, verify the bundle, and persist `envelope.json`.
- carrier commands: parse source, load timezone map, fetch/read carrier data, convert to canonical itinerary JSON, validate, build calendar, write private JSON/ICS artifacts, emit safe summary.

Carrier-specific runtime details live in the airline owner files under `../carriers/`, not in this file. The output bundle boundary lives in `output-bundle-design.md`.

## Verification gates

For normal `build` delivery:

1. Envelope has `schema_version == "flight-calendar-ics-cli.v1"`.
2. `ok == true` and `command == "build"`.
3. `data.route` matches the selected source route.
4. `data.segments_count >= 1`.
5. `data.ics_path` and `data.envelope_path` exist.
6. `data.verification.ok == true`.
7. Final chat summary excludes PNR keys, access keys, passenger names, ticket numbers, bearer tokens, fare/payment details, and full booking URLs.

The CLI's `verify_bundle` step owns the structural `.ics` checks: file modes, `BEGIN:VCALENDAR`, `VEVENT` count, UTC `DTSTART`/`DTEND`, and placeholder rejection. If using a direct command instead of `build`, the agent must still perform those checks externally.

## Test contract

Run from the skill root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_flight_calendar_ics_cli
```

The tests should assert:

- the single executable exists and emits the JSON envelope;
- `doctor` describes commands, entrypoint, `data.agent_contract`, and `build` dispatch templates without repeated output flags;
- actual `doctor`/`build`/happy-path/error envelopes validate against `schemas/cli-envelope.v1.schema.json`;
- `build make` creates a private bundle with `itinerary.json`, `flights.ics`, and `envelope.json`;
- `build <carrier>` wraps carrier commands with canonical bundle paths and supports `--url-file`;
- `validate` is check-only and machine-readable;
- direct `make` writes `.ics` with mode `0600`;
- each carrier command writes private artifacts with mode `0600` and keeps carrier-specific private values out of stdout/stderr;
- invalid alarms and usage errors return JSON errors, not tracebacks or raw argparse text;
- compatibility helper surfaces remain tested when they can write private artifacts.
