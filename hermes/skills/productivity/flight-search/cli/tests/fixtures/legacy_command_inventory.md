# Legacy command inventory

Snapshot for the `refactor_flights-search` branch before removing legacy route
command tails. This file intentionally records current references; later command
surface tests own the expected absence checks.

## Parser surface

- `search --request` is registered as the public Golden Path.
- `diagnose plan --request` is registered as the dry-planning diagnostic.
- `diagnose probe`, `diagnose render`, `diagnose kb-search`,
  `diagnose kb-roundtrip`, `diagnose fli-search`, and `diagnose fli-dates` are
  registered under `diagnose`.
- `route plan` is still registered in `flights_cli/cli.py`.
- `route validate`, `route rank`, and `route assemble` are still registered.
- Top-level `kb-search`, `kb-roundtrip`, `fli-search`, and `fli-dates` are not
  registered.
- `route live-assemble` and `route kb-assemble` are not registered.

## Command handlers

- `command_route_plan()` remains in `flights_cli/commands/route.py`.
- `command_route_live_assemble()` remains in `flights_cli/commands/route.py`.
- `command_route_kb_assemble()` is absent.
- `run_live_route_assembly()` remains imported by the search app.

## Docs

- `SKILL.md` names `search --request` as the Golden Path.
- `SKILL.md`, `README.md`, and active references still mention diagnostic
  provider probes such as `diagnose kb-search` and `diagnose fli-search`.
- Active references still describe `route plan` as an offline/development
  surface.

## Tests

- `tests/test_cli_contract.py` currently includes `route plan` in parser and
  catalog-refresh coverage.
- `tests/test_primary_cli_namespaces.py` currently includes `route plan` in
  parser coverage.
- Provider diagnostic tests cover the `diagnose ...` probe commands.

## Generated command strings and fixtures

- `flights_cli/orchestrators/route_plan.py` still generates legacy command
  strings containing `kb-search` or `fli-search` as non-canonical helper text.
- `route_plan_commands` remains in route-plan metrics and metrics-workflow
  assertions.
