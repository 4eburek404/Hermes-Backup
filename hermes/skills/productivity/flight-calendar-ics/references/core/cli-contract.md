# CLI Contract

This file explains the stable CLI contract. Deterministic behavior lives in `scripts/flight_calendar/contracts.py`, `schemas/cli-envelope.v1.schema.json`, parser errors/help, and tests.

## Stable surfaces

- Production happy path: `python scripts/flight_calendar_ics.py --json build auto --url-file /private/source-url.txt`.
- Canonical JSON happy path: `python scripts/flight_calendar_ics.py --json build auto --input /private/itinerary.json`.
- Diagnostics stay under `diagnose ...`.
- Maintenance stays under read-only `maint ...`.
- Root commands and explicit `build <carrier>` routes are compatibility/diagnostic surfaces, not the normal generation path.

The root wrapper `scripts/flight_calendar_ics.py` must stay thin. It delegates to the package parser/commands and must not grow business logic.

## JSON envelope v1

Every `--json` response uses:

- `schema_version = flight-calendar-ics-cli.v1`
- `ok: boolean`
- `command`
- `process[]`
- optional `data` or `error`

For successful `build ...` responses, `data.agent_handoff` is the code-owned delivery/reporting surface. Agents copy `data.agent_handoff.media` and `data.agent_handoff.safe_summary`; they do not open generated artifacts to recount events or modes.

Append fields only when possible. If `data` gains a new key, update the schema and a narrow contract test in the same slice because the schema uses `additionalProperties: false`.

## `doctor.data.agent_contract`

`doctor` exposes machine-readable agent guidance so `SKILL.md` can stay short:

- `normal_steps`: collect private source, run one build command, verify, deliver.
- `dispatch_matrix`: source type → command template.
- `verification`: envelope and private bundle invariants.
- `failure_path`: read JSON error code, do not switch route without new evidence, run diagnostics only after failure or explicit request.
- `diagnostics`: read-only diagnostic namespace summary.
- `maintenance`: read-only maint namespace summary and runtime-sync approval guard.
- `privacy`: chat-summary omission classes.

Do not duplicate this matrix in prose. Change `contracts.py`, schema, and tests first.

## Verification owner

Use these contract tests when changing the surface:

- `tests/test_command_surface_contract.py`
- `tests/test_maint_namespace_contract.py`
- `tests/test_entrypoint_wrapper_contract.py`
- `tests/test_privacy_and_envelope_contract.py`

Safe smoke checks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json doctor
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json diagnose doctor
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json maint contracts
```

## Privacy boundary

CLI stdout may contain safe paths, counts, route names, redacted evidence, and verification status. It must not print private source contents, full carrier links, passenger identity, ticket/document/contact/payment fields, authentication material, generated API headers, or `.ics` body text.
