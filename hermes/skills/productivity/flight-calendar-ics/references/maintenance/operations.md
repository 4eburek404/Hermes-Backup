# Maintenance Operations

This file consolidates source/runtime, layer-boundary, cleanup, and refactor runbooks for `flight-calendar-ics`.

## Boundary

- Production calendar creation remains `build auto`.
- Failed-build investigation uses `diagnose ...`.
- Package maintenance uses read-only `maint ...`.
- Do not create a separate maintenance skill for this package.
- Do not sync source changes into `~/.hermes/skills/...` without explicit approval.

## Read-only maintenance commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json maint contracts
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json maint refs registry-check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json maint source-runtime diff --source-dir <source> --runtime-dir <runtime>
PYTHONDONTWRITEBYTECODE=1 python3 scripts/flight_calendar_ics.py --json maint audit
```

These reports must include metadata only, not file contents or private booking data.

## Refactor/TDD sequence

Use small slices:

1. Add or update a positive contract test.
2. Run it and confirm RED for the missing behavior.
3. Implement the minimal code/schema/doc-owner change.
4. Run targeted tests GREEN.
5. Run broader compile/contract/smoke checks before reporting done.

Preferred slice order for this package:

1. contracts;
2. envelope/schema;
3. privacy;
4. route detection;
5. bundle;
6. build orchestration;
7. carrier adapters;
8. references/SKILL cleanup.

## Reference cleanup rules

- Distill deterministic behavior into CLI contracts, schema, parser/help/errors, diagnostics/maint reports, or tests.
- Keep conceptual/operator knowledge in references.
- Delete historical case files only after their durable rule is encoded or merged into an owner file.
- Update `references/registry.md` and run `maint refs registry-check` after renames/deletions.
- Fix incoming links before deleting files.

## Source/runtime checks

Source and runtime are separate layers. A source-branch cleanup is not runtime activation. Runtime sync requires explicit user approval and separate verification.

Report source/runtime checks as paths, counts, hashes/status, and changed path names only. Do not print file contents.
