# Layer Boundary: Production Calendar Creation vs Diagnostics/Maintenance

## Durable decision

`flight-calendar-ics` should remain one domain skill/package. Do **not** split debugging, cleanup, eval, source/runtime drift, registry maintenance, or contract validation into a separate `flight-calendar-ics-maintenance` skill.

Instead, keep the user-facing production path compact and move brittle or operator-only behavior behind CLI namespaces in the same package.

## Target layer model

- Production surface: `build auto`
  - privacy-first input handling;
  - route inference owned by CLI;
  - private output bundle creation owned by CLI;
  - envelope verification before delivery;
  - final response sends only `MEDIA:/.../flights.ics` plus a short operational summary.
- Diagnostic surface: `diagnose ...`
  - route inference probes;
  - carrier extraction probes;
  - contract/doctor-style checks;
  - used only when `build auto` fails or diagnostics are explicitly requested.
- Maintenance/admin surface: `maint ...`
  - source→runtime drift checks;
  - registry validation;
  - cleanup dry-runs;
  - eval/contract validation;
  - used only for skill maintenance work, not normal calendar generation.

## Preferred command shapes

These names are design targets, not a guarantee that every command already exists:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json diagnose doctor
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json diagnose route-detect --url-file /private/source-url.txt
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json diagnose carrier-probe <carrier> --url-file /private/source-url.txt
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json maint source-runtime diff
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json maint refs registry-check
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json maint clean --dry-run
```

## Planning rule

When asked to analyze/refactor this skill's architecture, write the plan in `/home/konstantin/docs/plans/` and treat the flight-search CLI refactor plan as the analogue:

`/home/konstantin/docs/plans/2026-06-08-flight-search-agent-cli-refactor.md`

The plan created from this decision is:

`/home/konstantin/docs/plans/2026-06-08-flight-calendar-ics-layer-split.md`

Before implementation, analyze current source→runtime drift and classify runtime-only files; do not run source→runtime sync without explicit approval.
