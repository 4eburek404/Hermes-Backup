# Architecture and CLI Contract

Conceptual boundaries and the stable CLI contract. Deterministic behavior lives in `scripts/flight_calendar/`, `schemas/`, parser errors/help, and tests — not in this prose.

## Layers

1. **Source evidence** — private carrier URL, ticket/receipt/PDF/email/screenshot, or canonical itinerary JSON.
2. **Route detection** — `build auto` chooses a route from safe fingerprints; known carrier hosts win before generic field names.
3. **Carrier/manual adapter** — converts source evidence into canonical itinerary segments (`flight_calendar/carriers/`, shared transport in `carrier_http.py`).
4. **Canonical validation** — schema plus semantic flight checks (`itinerary_contract.py`).
5. **Calendar renderer** — `.ics` with UTC event times (`ics_render.py`).
6. **Private bundle** — CLI-owned output directory: canonical JSON, `flights.ics`, `envelope.json`, private file modes (`bundle.py`).
7. **Envelope** — machine-readable success/error result for the agent (`envelope.py`).

Supporting owners: `parser.py` (command namespace, dispatch), `contracts.py` (command registry, `doctor.data.agent_contract`), `route_detection.py`, `build_command.py`, `privacy.py` (redaction), `timezone_catalog.py` + `data/airport-timezones.json`, `common.py`.

## Stable CLI surfaces

- Production happy path: `--json build auto --url-file /private/source-url.txt` (or `--input /private/itinerary.json` for canonical JSON).
- Explicit `build <route>` is a diagnostic surface; diagnostics live under `diagnose ...`; read-only maintenance under `maint ...`. There are no other root commands besides `doctor`.
- The wrapper `scripts/flight_calendar_ics.py` stays thin and must not grow business logic.

## JSON envelope v1

Every `--json` response carries `schema_version=flight-calendar-ics-cli.v1`, `ok`, `command`, `process[]`, and optional `data`/`error`. For successful builds, `data.agent_handoff` is the code-owned delivery surface: agents copy `media` and `safe_summary` and never open generated artifacts to recount events or modes.

The schema uses `additionalProperties: false` with shared vocabularies in `$defs`; append fields only, updating the schema and a narrow contract test in the same slice.

## `doctor.data.agent_contract`

`doctor` exposes machine-readable agent guidance (`normal_steps`, `dispatch_matrix`, `verification`, `failure_path`, `diagnostics`, `maintenance`, `privacy`) so `SKILL.md` stays short. Do not duplicate that matrix in prose; change `contracts.py`, the schema, and tests first.

## Agent boundary

The agent supplies private input paths, runs one CLI command for normal generation, parses the envelope, and sends the resulting media file. The agent does not own route dispatch, artifact names, file permissions, calendar verification, or generated-output plumbing on the happy path.

## Maintenance boundary

`diagnose ...` for failed builds or explicit diagnostic tasks; `maint ...` for read-only checks. Do not create a separate maintenance skill for this package. Runtime sync into `~/.hermes/skills/...` requires explicit approval.

## Verification owners

Contract tests: `test_command_surface_contract.py`, `test_maint_namespace_contract.py`, `test_entrypoint_wrapper_contract.py`, `test_privacy_and_envelope_contract.py`. Safe smokes: `--json doctor`, `--json diagnose doctor`, `--json maint contracts`.

CLI stdout privacy boundary: safe paths, counts, route names, redacted evidence, verification status only — sensitive classes are owned by `core/privacy-hardening.md`.
