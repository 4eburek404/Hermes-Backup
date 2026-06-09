# Architecture and Data Flow

This reference owns conceptual boundaries only. Deterministic command behavior belongs in `contracts.py`, parser code, schemas, and tests.

## Layers

1. **Source evidence** — private carrier URL, ticket/receipt/PDF/email/screenshot, or canonical itinerary JSON.
2. **Route detection** — `build auto` chooses a route from safe fingerprints. Known carrier hosts win before generic field names.
3. **Carrier/manual adapter** — converts source evidence into canonical itinerary segments.
4. **Canonical validation** — validates itinerary shape and semantic flight fields.
5. **Calendar renderer** — produces `.ics` with UTC event times and operational text.
6. **Private bundle** — CLI-owned output directory containing canonical JSON, `flights.ics`, and `envelope.json` with private file modes.
7. **Envelope** — machine-readable success/error result for the agent.

## Ownership

- `scripts/flight_calendar/parser.py`: command namespace, help, argument errors, JSON/CLI dispatch.
- `scripts/flight_calendar/contracts.py`: command registry and `doctor.data.agent_contract`.
- `scripts/flight_calendar/route_detection.py`: safe route inference and ambiguity errors.
- `scripts/flight_calendar/build_command.py`: build orchestration.
- `scripts/flight_calendar/bundle.py`: private output bundle and verification metadata.
- `scripts/flight_calendar/envelope.py`: envelope construction and persistence.
- `scripts/flight_calendar/privacy.py`: deterministic redaction helpers.
- `schemas/`: append-compatible JSON contracts.
- `tests/`: behavior that must not regress.

## Agent boundary

The agent supplies private input paths, runs one CLI command for normal generation, parses the envelope, and sends the resulting media file. The agent must not own route dispatch, artifact names, file permissions, calendar verification, or generated-output plumbing on the happy path.

## Maintenance boundary

Keep diagnostics and maintenance in this package:

- `diagnose ...` for failed builds or explicit diagnostic tasks.
- `maint ...` for read-only contract/reference/source-runtime checks.

Do not create a separate maintenance skill for this package unless the source package itself is split in the future.
