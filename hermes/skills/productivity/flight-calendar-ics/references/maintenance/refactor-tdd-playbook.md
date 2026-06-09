# Flight Calendar ICS Refactor TDD Playbook

Use this reference when refactoring the `flight-calendar-ics` skill package itself: splitting the CLI into modules, adding `diagnose`/`maint` surfaces, or cleaning source/runtime drift. This is maintenance guidance, not the normal `.ics` generation path.

## Session-derived rules

- Start from a clean source worktree based on `origin/main`; do not refactor in a dirty runtime skill directory.
- Treat runtime sync as a separate approval-gated operation. Source-only refactors may proceed, but copying into `~/.hermes/skills/...` needs explicit user approval when drift or private runtime state exists.
- Preserve the short production happy path while moving logic behind modules:

  ```bash
  python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --url-file /private/source-url.txt
  python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build auto --input /private/itinerary.json
  ```

- Keep root aliases only as temporary compatibility surfaces until tests can retire them; do not introduce a separate maintenance skill.
- Split surfaces by namespace:
  - `build ...` — production calendar creation.
  - `diagnose ...` — read-only diagnostics/doctor checks.
  - `maint ...` — read-only maintenance inspection such as registry/source-runtime drift checks.
- Use append-only schema evolution for `schemas/cli-envelope.v1.schema.json` unless an explicit version bump is required.

## TDD extraction sequence

1. Run baseline compile and the relevant existing unittest suite before edits.
2. Add a narrow RED contract test for the next module/surface.
3. When demonstrating RED in automation, preserve the failing exit code in output but return shell exit 0 only if you need to continue tool work:

   ```bash
   set +e
   PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_new_contract -v
   RC=$?
   echo "RED_EXIT=$RC"
   exit 0
   ```

4. Move one responsibility at a time from `scripts/flight_calendar_ics.py` into `scripts/flight_calendar/`.
5. Rewire imports through the new module; keep the wrapper moving toward a thin parser/entrypoint.
6. Run compile plus the touched contract tests and the legacy CLI tests after each slice.
7. Update `SKILL.md`, `references/registry.md`, and the maintenance reference that owns the changed behavior before final review.

## Proven slices

- `contracts.py`: command registry, route choices, command metadata, schema version, and agent contract payload.
- `envelope.py`: `CliFailure`, process steps, JSON envelope, JSON/human emitters, optional envelope artifact writing.
- `privacy.py`: stdout/stderr-safe redaction helpers; credential-like values become `[REDACTED]`.
- `route_detection.py`: `first_url_from_args`, known-host-first `infer_build_route`, and calendar-safe `safe_segment_summary`.
- Next useful slices: `bundle.py`, `timezones.py`, `segments.py`, then `build` command orchestration and carrier adapters.

## Privacy and output rules

- Tests and fixtures should use synthetic placeholders only.
- Do not print booking links, PNR keys, passenger names, tickets, documents, contacts, payments, API headers, bearer tokens, or access keys.
- Any credential-like value in command output, failure envelopes, or tests should be redacted to `[REDACTED]`.
- Module extraction should preserve private output directory creation, file mode checks, and calendar verification before `MEDIA:` delivery.

## Acceptance checkpoint

A refactor slice is complete only when:

- The new RED test failed for the intended reason before implementation.
- Compile passes for `scripts/*.py`, `scripts/flight_calendar/*.py`, and touched tests.
- All relevant contract tests pass, including legacy CLI behavior.
- The production happy path command remains unchanged.
- Runtime sync status is explicit: not touched, approved and synced, or blocked awaiting approval.
